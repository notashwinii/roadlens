# Design — RoadLens

A locked design system for the RoadLens product. App pages share this system.

## Genre

Modern-minimal, utilitarian operations software.

## App structure

- Persistent workspace sidebar.
- One page title and one primary action per route.
- Dense workbench panels for configuration and evidence.
- Empty states point to the next real action.

## Theme

- Near-white field-green paper.
- Near-black green-tinted ink.
- Field green is reserved for primary actions, focus, and healthy states.
- Surfaces use quiet borders; elevation is limited to dialogs and menus.

## Typography

- Display: Open Runde, weight 500–700, normal.
- Body: Geist Variable, weight 400–650.
- Headings use `-0.035em` to `-0.015em` tracking.
- Numeric data uses tabular figures.

## Spacing and shape

- 4px base spacing through named tokens in `tokens.css`.
- Controls are 40–44px high.
- Inputs and buttons use an 8px radius.
- Cards use a 10px radius.

## Components

- Use shared components from `frontend/src/components/ui`.
- Button, Input, Label, Card, Select, Switch, and Dialog follow shadcn APIs.
- Radix primitives provide accessible select, switch, and dialog behavior.
- Native controls are allowed only when a shared primitive would reduce usability.

## Motion

- 120–220ms state transitions.
- No page entrance animation.
- Reduced-motion removes nonessential transitions.

## Copy

- Short, concrete labels.
- No decorative kickers in app workflows.
- Explain complex configuration only where the user makes that choice.

## States

Interactive components provide default, hover, focus, active, disabled,
loading, error, and success styling where applicable.
