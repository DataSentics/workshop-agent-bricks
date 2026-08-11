# Workshop environment: deploy, run, inspect.
#
# databricks-config.yaml names the workspace, catalog and schemas, and every target
# reads it, so moving the workshop means editing that file and nothing else.
#
# `make deploy` is the happy path for a fresh workspace: it runs the scripts under
# workshop/demo_deployment_scripts in the order they depend on each other. It is not
# the only way in. Each script stands on its own, which is what you want when one
# piece has changed and redeploying everything would be silly:
#
#     uv run --with databricks-sdk --with pyyaml --with pyarrow python \
#         workshop/demo_deployment_scripts/deploy_genie.py
#
# Several accept --dry-run, and deploy_notebooks.py accepts --run to execute one
# notebook on serverless after publishing.

.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

.PHONY: help config auth generate deploy run/outlook run/casehub status

CONFIG  := databricks-config.yaml
UV      := uv run --quiet
SCRIPTS := workshop/demo_deployment_scripts
PY      := $(UV) --with databricks-sdk --with pyyaml --with pyarrow python

# Read one value out of the config. Evaluated at parse time, so the shell recipes
# below never have to know the file exists.
cfg = $(shell $(UV) --with pyyaml python -c \
        "import yaml;c=yaml.safe_load(open('$(CONFIG)'));print($(1))")

PROFILE     := $(call cfg,c['profile'])
CATALOG     := $(call cfg,c['unity_catalog']['catalog'])
SCHEMAS     := $(call cfg,' '.join(sorted(c['unity_catalog']['schemas'].values())))
DOCS_SCHEMA := $(call cfg,c['unity_catalog']['schemas'][c['volumes']['docs']['schema']])
DOCS_VOLUME := $(call cfg,c['volumes']['docs']['name'])
DOCS_PATH   := /Volumes/$(CATALOG)/$(DOCS_SCHEMA)/$(DOCS_VOLUME)

OUTLOOK_APP  := $(call cfg,c['apps']['outlook']['name'])
OUTLOOK_SRC  := $(call cfg,c['apps']['outlook']['source'])
CASEHUB_APP  := $(call cfg,c['apps']['casehub']['name'])
CASEHUB_SRC  := $(call cfg,c['apps']['casehub']['source'])
app_exclude   = $(call cfg,' '.join('--exclude '+p for p in c['apps'][$(1)]['exclude']))
APP_EXCLUDE  := $(call app_exclude,'outlook')
CASE_EXCLUDE := $(call app_exclude,'casehub')

OUTLOOK_SEED := $(call cfg,c['data']['dir']+'/'+c['data']['files']['outlook_seed'])

# The mailbox seed is copied into the app below and is .gitignored, so that the
# one copy under workshop/data stays the only one anybody edits. `databricks
# sync` honours .gitignore, which means it silently leaves the file behind: the
# app deploys without its seed, and every path that builds a mailbox from
# scratch - a new person opening Outlook, anybody pressing Reset demo - answers
# 500 with FileNotFoundError while everything else keeps working.
OUTLOOK_INCLUDE := --include src/app/data/outlook_seed.json

# Sync one app to the caller's workspace folder and deploy it from there.
# $(1) app name, $(2) source directory, $(3) --exclude flags, $(4) --include flags.
#
# The workspace copy is deleted first because `databricks sync` only adds and
# updates: after the move to a src/ layout the old flat app.py stayed behind,
# shadowed the installed package, and both apps crashed on start while the deploy
# still reported success.
define deploy_app
	@user=$$(databricks current-user me -p $(PROFILE) -o json \
	  | python3 -c "import sys,json;print(json.load(sys.stdin)['userName'])"); \
	path="/Workspace/Users/$$user/$(1)"; \
	echo "syncing $(2) -> $$path"; \
	databricks workspace delete "$$path" --recursive -p $(PROFILE) 2>/dev/null || true; \
	databricks sync --full $(2) "$$path" -p $(PROFILE) $(3) $(4); \
	databricks apps deploy $(1) --source-code-path "$$path" -p $(PROFILE) -o json \
	  | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])"
endef

##@ General

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make <target>\n"} \
	  /^[a-zA-Z0-9_\/-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 } \
	  /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)
	@echo
	@echo "Target: $(CATALOG) on profile '$(PROFILE)'"
	@echo

config: ## Print the resolved deployment target
	@echo "profile      $(PROFILE)"
	@echo "catalog      $(CATALOG)"
	@echo "schemas      $(SCHEMAS)"
	@echo "docs volume  $(DOCS_PATH)"
	@echo "outlook app  $(OUTLOOK_APP)"
	@echo "casehub app  $(CASEHUB_APP)"

auth: ## Check the configured profile can reach the workspace
	@databricks current-user me -p $(PROFILE) -o json \
	  | python3 -c "import sys,json;d=json.load(sys.stdin);print('authenticated as',d['userName'])"

status: ## Show what is currently deployed
	@$(PY) $(SCRIPTS)/status.py

##@ Deploy

deploy: ## Deploy the whole workshop: data, agents, apps, notebooks
	@$(PY) $(SCRIPTS)/seed_docs.py
	@$(PY) $(SCRIPTS)/deploy_knowledge_assistant.py
	@$(PY) $(SCRIPTS)/seed_tables.py
	@$(PY) $(SCRIPTS)/deploy_state.py
	@$(PY) $(SCRIPTS)/generate_attachments.py
	@$(PY) $(SCRIPTS)/deploy_functions.py
	@$(PY) $(SCRIPTS)/deploy_genie.py
	@$(PY) $(SCRIPTS)/deploy_search.py
	@echo "bundling $(OUTLOOK_SEED)"
	@mkdir -p $(OUTLOOK_SRC)/src/app/data
	@cp $(OUTLOOK_SEED) $(OUTLOOK_SRC)/src/app/data/outlook_seed.json
	$(call deploy_app,$(OUTLOOK_APP),$(OUTLOOK_SRC),$(APP_EXCLUDE),$(OUTLOOK_INCLUDE))
	$(call deploy_app,$(CASEHUB_APP),$(CASEHUB_SRC),$(CASE_EXCLUDE))
	@$(PY) $(SCRIPTS)/deploy_notebooks.py

##@ Develop

generate: ## Regenerate the committed datasets. Run before a workshop, then commit.
	@$(PY) $(SCRIPTS)/generate_employees.py
	@$(PY) $(SCRIPTS)/generate_payroll.py
	@$(PY) $(SCRIPTS)/generate_support.py
	@$(PY) $(SCRIPTS)/generate_outlook.py

run/outlook: ## Run the Outlook MCP app locally on http://127.0.0.1:8000
	@cd $(OUTLOOK_SRC) && uv run uvicorn app.main:create_application --factory \
	  --reload --host 127.0.0.1 --port 8000

run/casehub: ## Run the CaseHub agent locally on http://127.0.0.1:8001
	@cd $(CASEHUB_SRC) && DATABRICKS_CONFIG_PROFILE=$(PROFILE) \
	  uv run uvicorn app.main:create_application --factory \
	  --reload --host 127.0.0.1 --port 8001
