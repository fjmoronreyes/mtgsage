
# MtgSage

An evidence-grounded AI assistant for Magic: The Gathering.

## Overview

MtgSage is an AI engineering project developed as part of the
Turing Challenge technical assessment.

The goal is to design and implement an assistant capable of
answering questions about game rules, reasoning about card
interactions, and retrieving card information through external APIs.

The project emphasizes software quality, traceability,
testability, and informed architectural decisions.

## Objectives

- **Rules Q&A:** Answer gameplay questions using the official
  Magic: The Gathering Comprehensive Rules.
- **Card interactions:** Explain interactions between cards
  using relevant rules and card information.
- **Card discovery:** Translate natural-language requests
  into structured card searches.
- **Conversational context:** Maintain context across
  related user questions.
- **Custom cards (bonus):** Explore the generation of
  custom Magic cards.

## Engineering Principles

1. Evidence-grounded answers with traceable references.
2. Deterministic processing where appropriate.
3. Clear separation of application responsibilities.
4. Explicit handling of uncertainty and external failures.
5. Automated testing and reproducible environments.
6. Observable behavior, latency, and resource consumption.

## Technology

The initial development environment uses:

- Python 3.12
- Poetry
- Ubuntu 24.04 / WSL2
- Git and GitHub

Application frameworks, model providers, retrieval components,
and persistence technologies will be selected and documented
through architectural decisions.

## Project Structure

```text
MtgSage/
├── app/              # Application source code
├── data/             # Reference documents and data assets
├── docs/             # Architecture and technical documentation
├── tests/            # Automated tests
├── pyproject.toml    # Python project configuration
└── README.md
```

## Development Status

Initial project setup.

Implementation, evaluation, and execution instructions will
be added as the corresponding components are developed.
