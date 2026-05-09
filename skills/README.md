# PRIME Skills

Two types of skills live here.

## Cowork skills (`cowork/`)

These are prompt files for use during development sessions with Claude (Cowork mode). Load them when you want structured help with design decisions, architecture reviews, research briefs, or LinkedIn posts about the project.

Each file is a self-contained prompt. In a Cowork session, you can say "use the grill-me skill on this design" and Claude will follow the skill's instructions.

| Skill | When to use |
|-------|-------------|
| `grill-me.md` | Stress-test a plan or design before building it |
| `architecture.md` | Work through an ADR — context, decision, alternatives, consequences |
| `research-brief.md` | Structure research output before saving it to the knowledge base |
| `linkedin-posts.md` | Write LinkedIn posts in your voice about talks, articles, or ideas |

## Agent skills (`agents/`)

These are the system prompts loaded by PRIME's built-in agents when they execute tasks. Editing these changes how each agent type behaves — their persona, output format, and decision-making priorities.

| File | Agent |
|------|-------|
| `researcher.md` | Research agent — gathers, synthesises, saves findings |
| `writer.md` | Writer agent — documents, ADRs, summaries, briefs |
| `analyst.md` | Analyst agent — structured data analysis and reports |
| `monitor.md` | Monitor agent — watches sources, surfaces changes |

To swap an agent's behaviour, edit its `.md` file and restart the server (or reload the agent via the API).
