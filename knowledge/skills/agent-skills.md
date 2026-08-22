---
id: skill-agent-skills
title: Agent Skills Management
tags: [skill, agent-skills, management, workflow]
source: ~/my-skills/agent-skills/SKILL.md
imported_at: 2026-07-07
---
---
name: agent-skills
description: Production-grade engineering workflows for AI agents. Use when you need to ensure high-quality code, rigorous testing, security hardening, or structured planning. This skill provides a suite of specialized workflows for every phase of the software development lifecycle.
---

# Agent Skills: Production-Grade Engineering

## Overview

Agent Skills is a collection of production-grade engineering workflows designed to ensure AI agents produce high-quality, reliable, and secure code. These workflows enforce the discipline and best practices used by senior engineers.

## Skill Discovery

When a task arrives, identify the relevant development phase and refer to the corresponding reference file for detailed procedural guidance:

### 1. Define & Plan
- **Clarify intent**: Use [interview-me.md](references/interview-me.md) to surface what the user actually wants.
- **Refine ideas**: Use [idea-refine.md](references/idea-refine.md) for structured thinking about a concept.
- **Write specs**: Use [spec-driven-development.md](references/spec-driven-development.md) to define requirements before code.
- **Break down tasks**: Use [planning-and-task-breakdown.md](references/planning-and-task-breakdown.md) to decompose work into verifiable chunks.

### 2. Build & Implement
- **Core implementation**: Use [incremental-implementation.md](references/incremental-implementation.md) for vertical feature slices.
- **UI engineering**: Use [frontend-ui-engineering.md](references/frontend-ui-engineering.md) for accessible, polished interfaces.
- **API design**: Use [api-and-interface-design.md](references/api-and-interface-design.md) for stable, clear contracts.
- **Context management**: Use [context-engineering.md](references/context-engineering.md) to manage the agent's context window.
- **Doc-driven code**: Use [source-driven-development.md](references/source-driven-development.md) to verify against official documentation.
- **Adversarial review**: Use [doubt-driven-development.md](references/doubt-driven-development.md) for cross-examining non-trivial decisions.

### 3. Verify & Debug
- **TDD**: Use [test-driven-development.md](references/test-driven-development.md) for a test-first approach.
- **Browser testing**: Use [browser-testing-with-devtools.md](references/browser-testing-with-devtools.md) for runtime verification.
- **Debugging**: Use [debugging-and-error-recovery.md](references/debugging-and-error-recovery.md) for structured troubleshooting.

### 4. Review & Optimize
- **Code review**: Use [code-review-and-quality.md](references/code-review-and-quality.md) for 5-axis quality checks.
- **Simplify code**: Use [code-simplification.md](references/code-simplification.md) to reduce complexity.
- **Security**: Use [security-and-hardening.md](references/security-and-hardening.md) for OWASP standards and hardening.
- **Performance**: Use [performance-optimization.md](references/performance-optimization.md) for measurement-based optimization.

### 5. Ship & Maintain
- **Git workflow**: Use [git-workflow-and-versioning.md](references/git-workflow-and-versioning.md) for clean, atomic commits.
- **CI/CD**: Use [ci-cd-and-automation.md](references/ci-cd-and-automation.md) for automated quality gates.
- **Documentation**: Use [documentation-and-adrs.md](references/documentation-and-adrs.md) to document the "why" (ADRs).
- **Migration**: Use [deprecation-and-migration.md](references/deprecation-and-migration.md) for safe system transitions.
- **Shipping**: Use [shipping-and-launch.md](references/shipping-and-launch.md) for pre-launch checklists.

## Core Operating Behaviors

These behaviors apply across all workflows:
1. **Surface Assumptions**: Explicitly state assumptions before starting non-trivial work.
2. **Manage Confusion**: Stop and clarify when faced with inconsistencies.
3. **Push Back**: Propose better alternatives when an approach has clear downsides.
4. **Enforce Simplicity**: Resist overcomplication; prefer obvious, boring solutions.
5. **Verify, Don't Assume**: A task is only complete when verified with evidence (tests, logs).

## How to Use These References
When you activate this skill, refer to the table above. If you are starting a new feature, read `spec-driven-development.md` and `planning-and-task-breakdown.md` first. For implementation, load `incremental-implementation.md`. 

**Tip**: You can use `grep_search` to find specific rules within the reference files if they are large.
