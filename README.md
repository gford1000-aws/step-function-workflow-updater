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

* __[inject_workflow_macro.cform](inject_workflow_macro.cform)__ which deploys the macro 

* __[step_function_workflow_updater.cform](step_function_workflow_updater.cform)__ which is a basic CloudFormation template that can 
deploy a stack containing a StateMachine and its associated IAM Role.  The template invokes the macro to construct the workflow JSON attribute,
based on the value of the S3Key parameter (which is of the form `s3://BUCKET_NAME/KEY`)

* __[deploy_step_function_workflow.py](deploy_step_function_workflow.py)__ which is a helper script to manage updates to stacks containing a
StateMachine, whenever its associated workflow definition is changed.  This script will save the JSON workflow to S3 and then create a new
Change Set in CloudFormation, prior to execution.  The idea is that this script can be used as a commit hook for workflow updates.


## Licence

This project is released under the MIT license. See [LICENSE](LICENSE) for details.
