MAKEFLAGS += --warn-undefined-variables
SHELL = /bin/bash -o pipefail
.DEFAULT_GOAL := help
.PHONY: help clean test outdated

## display help message
help:
	@awk '/^##.*$$/,/^[~\/\.0-9a-zA-Z_-]+:/' $(MAKEFILE_LIST) | awk '!(NR%2){print $$0p}{p=$$0}' | awk 'BEGIN {FS = ":.*?##"}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' | sort

## all artifacts
all: PatchLinux.sh patch-baseline-operations

AWS-RunPatchBaseline.json:
	aws ssm get-document --name AWS-RunPatchBaseline --query 'Content' --output text > AWS-RunPatchBaseline.json

## PatchLinux.sh
PatchLinux.sh: AWS-RunPatchBaseline.json
	jq -r '.mainSteps[] | select(.name == "PatchLinux") | .inputs.runCommand[]' AWS-RunPatchBaseline.json > PatchLinux.sh

## patch-baseline-operations
patch-baseline-operations:
	aws s3 cp s3://aws-ssm-us-east-1/patchbaselineoperations/linux/payloads/patch-baseline-operations-1.80.tar.gz /tmp/patch-baseline-operations-1.80.tar.gz
	mkdir patch-baseline-operations
	tar -xvf /tmp/patch-baseline-operations-1.80.tar.gz -C patch-baseline-operations
