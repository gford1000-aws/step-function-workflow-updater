# step-function-workflow-updater

It is often desirable to separate the ability of development teams between writing application code (consuming data from infrastructure
resources and creating new data, to be stored in other resources or returned to callers) from the management of the underlying 
infrastructure itself.

With serverless programming in AWS Lambda and AWS StepFunctions, this means that dev teams need to be able to create and deploy Lambdas
(stateless application code) and StateMachine workflows (which orchestrate the Lambda invocation sequence), whilst ensuring
separate control of the infrastructure resources (DBs, StateMachines etc.) and the data within them (via IAM policies).

This repo provides an example of how to achieve this, whereby the JSON definition of the workflow can be managed outside of its 
deployment via CloudFormation, so that the separation of security privilege can be maintained.

The approach leverages the use of CloudFormation [macros](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-macros.html) to inject the new workflow JSON into the StateMachine resource as part of a CloudFormation Change Set.

Artefacts in the repo:

* __[inject_workflow_macro.cform](inject_workflow_macro.cform)__ which deploys the macro.  

* __[step_function_workflow_updater.cform](step_function_workflow_updater.cform)__ which is a basic CloudFormation template that can 
deploy a stack containing a StateMachine and its associated IAM Role.  The template invokes the macro to construct the workflow JSON attribute,
based on the value of the S3Key parameter (which is of the form `s3://BUCKET_NAME/KEY`)

* __[deploy_step_function_workflow.py](deploy_step_function_workflow.py)__ which is a helper script to manage updates to stacks containing a
StateMachine, whenever its associated workflow definition is changed.  This script will save the JSON workflow to S3 and then create a new
Change Set in CloudFormation, prior to execution.  The idea is that this script can be used as a commit hook for workflow updates.

## inject_workflow_macro.cform

This is a simple Cloudformation template to declare the Lambda and associate it with the Cloudformation Macro:

![alt text](https://github.com/gford1000-aws/step-function-workflow-updater/blob/master/inject%20workflow%20macro.png "Script per designer")

### Arguments

| Argument                     | Description                                                                 |
| ---------------------------- |:---------------------------------------------------------------------------:|
| MacroName                    | Name of the Cloudformation Macro, as used in other templates                |
| WorkflowBucketName           | Bucket which will contain the JSON workflows to be injected                 |
| MacroLogTTL                  | TTL of CloudWatch logs for the Lambda function                              |


### Outputs

| Output                  | Description                                                    |
| ----------------------- |:--------------------------------------------------------------:|
| MacroName               | The name of Macro                                              |


### Notes

* The macro will traverse the internet to access the specified S3 key; to prevent this, operate the Lambda within a VPC.  [https://github.com/gford1000-aws/lambda_s3_access_using_vpc_endpoint](https://github.com/gford1000-aws/lambda_s3_access_using_vpc_endpoint) provides an example of how to achieve this.  
* The macro is linked to an 
[alias](https://docs.aws.amazon.com/lambda/latest/dg/versioning-aliases.html) rather than the Lambda itself - this allows the Lambda to be easily changed/tested if required.
* The created role provides full read access to the specified bucket - this scope should reduced if the bucket is used for other activities.




## Licence

This project is released under the MIT license. See [LICENSE](LICENSE) for details.
