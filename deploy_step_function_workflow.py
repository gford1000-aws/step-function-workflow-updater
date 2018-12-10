""" ---------------------------------------------------------------------------

	File: deploy_step_function_workflow.py

	Description:
	------------

	Trigger an update to an existing CloudFormation Stack whenever a new Step Function workflow is changed.

	Idea is that this script can be added as a commit hook for workflow JSON changes, so that CloudFormation
	can be used to manage the StateMachine via ChangeSets as the workflows change.

	Principles:
	-----------

	Updates to workflows should be performed via CloudFormation to have a consistent and auditable 
	deployment strategy (rather than say, by a direct call to boto3.client('stepfunctions').update_state_machine() ).

	Separate the creation/changes of Step Function workflows, which will be managed by the dev team as part 
	of application development, from the infrastructure that the application is running within 
	(i.e. StateMachine and other AWS resources), to minimise IAM privileges needed by dev team.

	Only the team managing CloudFormation should have access to Macros, since these can potentially change any part of a
	CloudFormation template.

	Approach:
	---------

	Since the workflow is a string based attribute of the StateMachine CloudFormation resource type,
	a macro is required to load the revised workflow as JSON, stringify it, and then update the CloudFormation
	template with the change.  This is achieved using a CloudFormation ChangeSet which receives the
	same template each time, but the presence of the macro triggers the ChangeSet to execute the underlying
	Lambda function to check for changes - the Lambda then loads the JSON and updates the template with the new details.

	The required macro Stack is created via 'inject_workflow_macro.cform' (which includes the Lambda as embedded python).

	Example:
	--------

	An example template that supports updates is 'step_function_workflow_updater.cform', which creates a single
	StateMachine and its associated Role, returning the AWS Arns of both resources.  The Role Arn is useful so that 
	its policies can be updated, dependent on the workflow that the StateMachine will execute - by default the Role 
	has no access to any AWS resources.

	An example workflow JSON file is 'hello.json', which declares a trivial hello world workflow.

	Once the macro stack has been created (using the default parameters), then create the StateMachine stack using the
	CloudFormation console with a stack name of your choice.

	Then updating the stack to use the workflow JSON in hello.json is a call:

	python deploy_step_function_workflow.py 
		-b <YOUR S3 BUCKET> 
		-k hello.json -f hello.json 
		-s <YOUR STACK NAME>
		-t step_function_workflow_updater.cform 
		-d "A description of the ChangeSet - for example, this could be the commit id of the hello.json file"

"""

import boto3
import json
import os.path
import time
import uuid

def _check_parameters(param_name, param_value, post_check_fn_list=None):
	if param_value == None:
		raise Exception("{} must not be None".format(param_name))
	if not isinstance(param_value, (str, unicode)):
		raise Exception("{} must be a str or unicode value".format(param_name))
	if post_check_fn_list:
		if isinstance(post_check_fn_list, list):
			for fn in post_check_fn_list:
				fn(param_name, param_value)
		else:
			post_check_fn_list(param_name, param_value)

def _check_file_exists(param_name, param_value):
	if not os.path.isfile(param_value): 
		raise Exception("Specified file '{}' does not exist or is not a file".format(param_value))		

def save_workflow_to_s3(**kwargs):
	"""
	Saves the contents of the SourceFileName to the specified Key in Bucket

	Parameters:

		Bucket 			The name of the bucket
		Key 			The key to store the workflow within the bucket
		SourceFileName	The location of the file containing the workflow
		S3StorageClass	The type of S3 storage.  Must be one of STANDARD|STANDARD_IA|ONEZONE_IA

	Returns:

		Nothing

	"""
	def check_bucket_exists(param_name, param_value):
		client = boto3.client('s3')
		for bucket_info in client.list_buckets()["Buckets"]:
			if bucket_info["Name"] == param_value:
				return

		raise Exception("Specified bucket '{}' does not exist".format(param_value))

	def check_storage_class(param_name, param_value):
		if param_value not in [ "STANDARD", "STANDARD_IA", "ONEZONE_IA" ]:
			raise Exception("{} must be one of [STANDARD|STANDARD_IA|ONEZONE_IA]".format(param_name))

	if kwargs is None:
		raise Exception("Incorrect parameters supplied to save_workflow_to_s3()")

	# Check parameters
	_check_parameters("Bucket", kwargs.get("Bucket", None), check_bucket_exists)
	_check_parameters("Key", kwargs.get("Key", None))
	_check_parameters("SourceFileName", kwargs.get("SourceFileName", None), _check_file_exists)
	_check_parameters("S3StorageClass", kwargs.get("S3StorageClass", None), check_storage_class)

	# Upload file to S3
	client = boto3.client('s3')
	client.put_object(
		Bucket=kwargs["Bucket"],
		Key=kwargs["Key"],
		Body=open(kwargs["SourceFileName"], "r"),
		ContentType="application/json",
		StorageClass="STANDARD")

def update_stack(**kwargs):
	"""
	Creates a ChangeSet and then Executes if changes are detected.

	Using a ChangeSet ensures that Macros are re-executed, to detect all changes, in this case
	the modification to the StateMachine workflow saved to S3

	Parameters:

		StackName					The name of the stack to be updated.  Stack must already exist and be updateable
		TemplateFileName			The location of the template with which to update the stack.
		S3KeyParameterName			The name of the parameter that identifies the S3 object key holding the revised workflow
		S3Key 						The S3 key to assign to the S3KeyParameter
		SMResourceParameterName		The name of the parameter that identifies the StateMachine resource to be updated
		SMResource 					The logical resource name to assign to the SMResourceParameter
		Description 				The description for this stack update

	Returns:

		Nothing

	"""

	def check_stack_exists_and_updatable(param_name, param_value):
		client = boto3.client('cloudformation')
		resp = client.list_stacks(StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE"])
		cont = True
		while cont:
			for stack in resp["StackSummaries"]:
				if stack["StackName"] == param_value:
					return # Exists and ready for update
			next_token = resp.get("NextToken", None)
			if next_token:
				resp = client.list_stacks(StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE"], NextToken=next_token)
			else:
				cont = False
		raise Exception("Specified Stack '{}'' either does not exist or is not ready for update".format(param_value))

	def check_template_params_exist(param_name, param_value):
		template = json.load(open(param_value, "r"))
		template_parameters = template.get("Parameters", {})
		for template_param_name in [kwargs["S3KeyParameterName"], kwargs["SMResourceParameterName"]]:
			if template_parameters.get(template_param_name, None) == None:
				raise Exception("Parameter '{}' not present in template '{}'".format(template_param_name, param_value))
			else:
				del template_parameters[template_param_name]

		if len(template_parameters):
			# Error if further parameters in the template, with no default value
			for k, v in template_parameters.viewitems():
				if v.get("Default", None) == None:
					raise Exception("Additional parameters in template '{}' without defaults (e.g. '{}')".format(param_value, k))

	def wait_for_change_set(change_set_id):
		resp = client.describe_change_set(ChangeSetName=change_set_id)
		sleep_time = 2
		while resp['Status'] not in ["CREATE_COMPLETE", "FAILED"]:
			time.sleep(sleep_time)
			sleep_time = sleep_time * 2 # To avoid throttling errors due to too many calls to describe_change_set
			resp = client.describe_change_set(ChangeSetName=change_set_id)
		return resp

	if kwargs is None:
		raise Exception("Incorrect parameters supplied to save_workflow_to_s3()")

	# Check parameters
	_check_parameters("StackName", kwargs.get("StackName", None), check_stack_exists_and_updatable)
	_check_parameters("TemplateFileName", kwargs.get("TemplateFileName", None), [_check_file_exists, check_template_params_exist])
	_check_parameters("S3KeyParameterName", kwargs.get("S3KeyParameterName", None))
	_check_parameters("S3Key", kwargs.get("S3Key", None))
	_check_parameters("SMResourceParameterName", kwargs.get("SMResourceParameterName", None))
	_check_parameters("SMResource", kwargs.get("SMResource", None))

	# Create ChangeSet for the Stack
	print 'Creating Change Set'
	client = boto3.client('cloudformation')
	resp = client.create_change_set(
		StackName=kwargs["StackName"],
		TemplateBody=open(kwargs["TemplateFileName"], "r").read(),
		Parameters=[
				{
					"ParameterKey" : kwargs["S3KeyParameterName"],
					"ParameterValue" : kwargs["S3Key"],
					"UsePreviousValue" : False
				},
				{
					"ParameterKey" : kwargs["SMResourceParameterName"],
					"ParameterValue" : kwargs["SMResource"],
					"UsePreviousValue" : False
				}
			],
		Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
		Description=kwargs["Description"],
		ChangeSetName='A'+''.join(str(uuid.uuid4()).split("-")),
		ChangeSetType="UPDATE")

	# Determine state of the ChangeSet
	print 'Waiting on Change Set creation'
	change_set_id = resp['Id']
	resp = wait_for_change_set(change_set_id)

	# Validate the expected StateMachine resource is being updated
	print 'Validating Change Set status'

	if resp["Status"] == "FAILED":
		raise Exception("ChangeSet '{}' creation FAILED - '{}'".format(change_set_id, resp["StatusReason"]))

	found_required_change = False
	for chg in resp['Changes']:
		if chg['ResourceChange']['LogicalResourceId'] == kwargs["SMResource"]:
			# The target StateMachine will be updated
			found_required_change = True
			break

	if not found_required_change:
		raise Exception("ChangeSet '{}' does not modify StateMachine '{}' - check workflow file".format(change_set_id, kwargs["SMResource"]))

	# Execute Change Set to apply the changes
	print 'Applying Change Set'
	client.execute_change_set(ChangeSetName=change_set_id)

	print 'Waiting on Change Set execution'
	resp = wait_for_change_set(change_set_id)

	if resp["Status"] == "FAILED":
		raise Exception("ChangeSet '{}' execution FAILED - '{}'".format(change_set_id, resp["StatusReason"]))

	if resp["ExecutionStatus"] != "AVAILABLE":
		raise Exception("ChangeSet '{}' execution status is '{}'".format(change_set_id, resp["ExecutionStatus"]))

	print 'Update has completed successfully'

def update_workflow(**kwargs):
	"""
	Updates S3 and then updates the stack
	"""
	print 'Saving updated Workflow'
	save_kwargs = {k:v for k,v in filter(lambda t: t[0] in ["Bucket", "Key", "SourceFileName", "S3StorageClass"], kwargs.items()) }
	save_workflow_to_s3(**save_kwargs)

	print 'Updating StateMachine stack'
	update_kwargs = {k:v for k,v in filter(lambda t: t[0] in ["StackName", "Description", "TemplateFileName", "S3KeyParameterName", "SMResourceParameterName", "SMResource"], kwargs.items()) }
	update_kwargs["S3Key"] = "s3://{}/{}".format(kwargs["Bucket"], kwargs["Key"])
	update_stack(**update_kwargs)

if __name__ == "__main__":
	import argparse
	parser = argparse.ArgumentParser(description="Demos how a commit hook on workflow JSON file changes could trigger a CloudFormation update of the State Machine")
	parser.add_argument("-b", "--Bucket", help="S3 bucket which stores the workflow JSON files", required=True)	
	parser.add_argument("-k", "--Key", help="S3 key which identifies the workflow JSON file", required=True)	
	parser.add_argument("-f", "--SourceFileName", help="Filename of the workflow JSON to be saved to S3", required=True)
	parser.add_argument("-d", "--Description", help="Description of the ChangeSet to the Stack (e.g. Commit)", default="")
	parser.add_argument("-s", "--StackName", help="Name of the Stack to be updated", required=True)
	parser.add_argument("-t", "--TemplateFileName", help="Filename of the template of the Stack to be updated", required=True)
	parser.add_argument("-c", "--S3StorageClass", help="S3 storage class to use for the JSON workflow file", default="STANDARD")
	parser.add_argument("-p1", "--S3KeyParameterName", help="Name of S3Key parameter in the Stack template", default="S3Key")
	parser.add_argument("-p2", "--SMResourceParameterName", help="Name of StateMachine parameter in the Stack template", default="SMResource")
	parser.add_argument("-v2", "--SMResource", help="Name of StateMachine resource in the Stack template, to assign to SMResourceParameterName", default="MyStateMachine")

	args = parser.parse_args()	

	update_workflow(
		Bucket=args.Bucket,
		Key=args.Key,
		SourceFileName=args.SourceFileName,
		S3StorageClass=args.S3StorageClass,
		StackName=args.StackName,
		Description=args.Description,
		TemplateFileName=args.TemplateFileName,
		S3KeyParameterName=args.S3KeyParameterName,
		SMResourceParameterName=args.SMResourceParameterName,
		SMResource=args.SMResource)
