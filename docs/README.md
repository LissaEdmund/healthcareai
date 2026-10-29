# Documentation Index

| File | Contents | Consult when… |
|---|---|---|
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | Purpose, users, scope, constraints, non-goals | starting any work; judging whether a feature is in scope |
| [REQUIREMENTS.md](REQUIREMENTS.md) | FR/NFR with acceptance criteria | implementing or testing a feature |
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | Components, data flow, boundaries, error handling (as implemented) | changing how components interact |
| [MODULES.md](MODULES.md) | Module list, files, status | finding code; updating status after a change |
| [DATABASE_DESIGN.md](DATABASE_DESIGN.md) | Tables, constraints, migrations | changing the schema |
| [API_REFERENCE.md](API_REFERENCE.md) | HTTP endpoints, permissions, errors | changing or calling the API |
| [MCP_TOOLS.md](MCP_TOOLS.md) | Original and borrowed MCP servers, schemas, restrictions | changing tools or filesystem access |
| [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) | LangGraph state machine, approval checkpoint, recovery | changing the workflow |
| [CLINICAL_SAFETY.md](CLINICAL_SAFETY.md) | Prohibitions and how they are enforced | any change touching evidence, proposals, summaries or actions |
| [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) | Auth, tokens, secrets, logging, gaps | security-relevant changes |
| [USER_ROLES_AND_PERMISSIONS.md](USER_ROLES_AND_PERMISSIONS.md) | Role × permission matrix, delegation scopes | adding routes/tools or roles |
| [UI_UX_SPECIFICATION.md](UI_UX_SPECIFICATION.md) | Screens, states, accessibility | frontend work |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Test layers and commands | writing tests |
| [EVALS.md](EVALS.md) | Evaluation scenarios with actual results | reporting status; regression checks |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Exact setup and run commands | installing or running |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Encountered problems and verified fixes | something breaks |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Phases, acceptance criteria, blockers | planning next work |
| [DECISIONS.md](DECISIONS.md) | Decision log | before reversing a design choice |
| [CHANGELOG.md](CHANGELOG.md) | Dated changes | release notes |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | Three-minute demo walkthrough | presenting |
| [memory.md](memory.md) | Development memory: snapshot, change history, next steps | **first thing in every new session** |
