# Rotorflight agent skills

Skills for coding agents (Claude Code, Codex, Gemini CLI and others) that work on
[Rotorflight](https://github.com/rotorflight). Each skill is a folder under [skills/](skills/)
with a `SKILL.md` in the [Agent Skills](https://agentskills.io) format: a short front matter
that says when to use it, followed by the instructions.

The skills cover workflows that span several Rotorflight repositories or need local tools.
Rules that belong to a single repository stay in that repository's `AGENTS.md`, and these
skills link to them instead of copying them.

## Skills

| Skill | Use it to |
| --- | --- |
| [firmware-toolchain](skills/firmware-toolchain/SKILL.md) | Install the Arm toolchain with the firmware makefile and build a target |
| [firmware-unit-tests](skills/firmware-unit-tests/SKILL.md) | Run the firmware unit tests (`make test`) |
| [firmware-sitl](skills/firmware-sitl/SKILL.md) | Build and run the firmware as a host process (SITL) |
| [jlink-debug](skills/jlink-debug/SKILL.md) | Debug a flight controller over SWD with a SEGGER J-Link |
| [blackbox-decode](skills/blackbox-decode/SKILL.md) | Decode blackbox logs with the Blackbox Explorer parser and analyse them in Python |
| [edgetx-simulator](skills/edgetx-simulator/SKILL.md) | Run the EdgeTX Lua suite in the EdgeTX simulator |
| [ethos-simulator](skills/ethos-simulator/SKILL.md) | Run the Ethos Lua suite in the Ethos simulator |
| [ethos-real-radio](skills/ethos-real-radio/SKILL.md) | Drive and debug a real Ethos radio over USB |

## Install

**Claude Code**, as a plugin:

```
/plugin marketplace add rotorflight/rotorflight-agent-skills
/plugin install rotorflight-dev@rotorflight
```

A repository can offer it to every contributor by listing the marketplace in its
`.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "rotorflight": {
      "source": { "source": "github", "repo": "rotorflight/rotorflight-agent-skills" }
    }
  },
  "enabledPlugins": { "rotorflight-dev@rotorflight": true }
}
```

**Other agents:** clone this repository next to the Rotorflight repositories and read the
`SKILL.md` of the skill you need. Copying a skill folder into the agent's skills directory
(for example `~/.codex/skills/` or `~/.claude/skills/`) also works.

## Contributing

- One task per skill. Name the folder after the task, and say in `description` when to use it.
- Link to the source of truth (a makefile, a README, a vendor page) instead of copying it.
  Keep only what an agent cannot find there: the order of the steps, the platform pitfalls,
  and what to check afterwards.
- No personal paths, serial numbers or tokens.
- Test a change by asking an agent to do the task with only the skill to go on.

## License

GPL-3.0, like the rest of Rotorflight. See [LICENSE](LICENSE).
