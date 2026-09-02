# One entry point. Every target that could touch AWS exports the three variables
# that keep it in the prototype's own account — the machine's default profile is
# an administrator of a different one, and a bare call reaches it and succeeds.
export AWS_SHARED_CREDENTIALS_FILE ?= $(HOME)/.aws/bedrock-personal
export AWS_CONFIG_FILE             ?= $(HOME)/.aws/bedrock-personal-config
export AWS_PROFILE                 ?= bedrock
export AWS_REGION                  ?= us-east-1
export AWS_EC2_METADATA_DISABLED   ?= true
# Deliberately not defaulted here. bedrock.py refuses without it, and a value
# written into a public repository would both contradict that and publish the
# account number. Put it in .env, which is not tracked.
-include .env
export BEDROCK_ACCOUNT_ID

PY := .venv/bin/python
SPEC_TAG ?= spec-v2.3

.PHONY: setup model-sync model-verify model-verify-remote leak-scan fixtures test live aws whoami clean

setup:                     ## venv, dependencies, and the tools that are not pip
	python3 -m venv .venv
	$(PY) -m pip -q install --upgrade pip
	$(PY) -m pip -q install pyyaml pytest z3-solver boto3 google-genai
	@command -v opa   >/dev/null || { echo "opa is missing: brew install opa"; exit 1; }
	@command -v swipl >/dev/null || { echo "swipl is missing: brew install swi-prolog"; exit 1; }
	@echo "setup ok"

model-sync:                ## vendor the specification's model at $(SPEC_TAG)
	$(PY) tools_model_sync.py $(SPEC_TAG)

model-verify:              ## local copy against the lock — no network
	$(PY) tools_model_sync.py verify

model-verify-remote:       ## also re-fetch the tag; for CI, not for a laptop offline
	$(PY) tools_model_sync.py verify --remote

leak-scan:                 ## every name under fixtures/ must be one we invented
	$(PY) tools_allowlist_scan.py

fixtures:                  ## parse every fixture and check it against the universe
	@$(PY) -c "import yaml,pathlib,sys; \
	[yaml.safe_load(p.read_text(encoding='utf-8')) for p in pathlib.Path('fixtures').rglob('*.yaml')]; \
	print('fixtures parse')"
	$(PY) tools_allowlist_scan.py

test:                      ## unit tests; no network, no AWS account reachable
	$(PY) -m pytest tests -q -m "not live"

live:                      ## the few tests that need the real provider
	LIVE=1 $(PY) -m pytest tests -q -m live

aws:                       ## the only sanctioned way to run the CLI: make aws ARGS="bedrock list-guardrails"
	@test -n "$(ARGS)" || { echo 'usage: make aws ARGS="bedrock list-guardrails"'; exit 1; }
	@$(MAKE) --no-print-directory whoami >/dev/null
	aws $(ARGS)

whoami:                    ## which AWS account a live run would use
	@$(PY) -c "import sys; sys.path.insert(0,'.'); \
	from gateway.provider.bedrock import session; \
	i = session().client('sts').get_caller_identity(); \
	print(i['Account'], i['Arn'])"

clean:
	rm -rf .venv **/__pycache__ .pytest_cache
