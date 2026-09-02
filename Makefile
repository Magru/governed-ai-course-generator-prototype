# One entry point. Every target that could touch AWS exports the three variables
# that keep it in the prototype's own account — the machine's default profile is
# an administrator of a different one, and a bare call reaches it and succeeds.
export AWS_SHARED_CREDENTIALS_FILE ?= $(HOME)/.aws/bedrock-personal
export AWS_CONFIG_FILE             ?= $(HOME)/.aws/bedrock-personal-config
export AWS_PROFILE                 ?= bedrock
export AWS_REGION                  ?= us-east-1
export AWS_EC2_METADATA_DISABLED   ?= true
export BEDROCK_ACCOUNT_ID          ?= 631412641947

PY := .venv/bin/python
SPEC_TAG ?= spec-v2.2

.PHONY: setup model-sync model-verify leak-scan fixtures test whoami clean

setup:                     ## venv, dependencies, and the tools that are not pip
	python3 -m venv .venv
	$(PY) -m pip -q install --upgrade pip
	$(PY) -m pip -q install pyyaml pytest z3-solver boto3 google-genai
	@command -v opa   >/dev/null || { echo "opa is missing: brew install opa"; exit 1; }
	@command -v swipl >/dev/null || { echo "swipl is missing: brew install swi-prolog"; exit 1; }
	@echo "setup ok"

model-sync:                ## vendor the specification's model at $(SPEC_TAG)
	$(PY) tools_model_sync.py $(SPEC_TAG)

model-verify:              ## fail if the vendored copy has drifted from the tag
	$(PY) tools_model_sync.py verify

leak-scan:                 ## every name under fixtures/ must be one we invented
	$(PY) tools_allowlist_scan.py

fixtures:                  ## parse every fixture and check it against the universe
	@$(PY) -c "import yaml,pathlib,sys; \
	[yaml.safe_load(p.read_text(encoding='utf-8')) for p in pathlib.Path('fixtures').rglob('*.yaml')]; \
	print('fixtures parse')"
	$(PY) tools_allowlist_scan.py

test:                      ## unit tests; cannot reach any real AWS account
	$(PY) -m pytest tests -q

whoami:                    ## which AWS account a live run would use
	@$(PY) -c "import sys; sys.path.insert(0,'.'); \
	from gateway.provider.bedrock import session; \
	i = session().client('sts').get_caller_identity(); \
	print(i['Account'], i['Arn'])"

clean:
	rm -rf .venv **/__pycache__ .pytest_cache
