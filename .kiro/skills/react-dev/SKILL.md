---
name: react-dev
description: Develop React components for DDM v2 frontend following project structure
---

# React Frontend Development for DDM v2

Develop or review React TypeScript components following DDM v2 frontend patterns:

## Project Structure
- **Feature Organization**: Components in `src/frontend/src/features/<tab>/`
- **Shared Components**: Reusable UI in `src/frontend/src/shared/`
- **API Integration**: Use TanStack Query for server state management
- **State Management**: Zustand for client state, React Query for server state

## Technology Stack
- **React 19**: Latest React features and patterns
- **TypeScript**: Strict type checking enabled
- **Vite 6**: Build tool and dev server
- **TailwindCSS**: Utility-first styling
- **Playwright**: E2E testing framework

## Development Patterns
- **Modular Architecture**: Each tab is a self-contained feature module
- **API-Driven**: All data via `/api/v2` endpoints with proper typing
- **Responsive Design**: Mobile-first approach with Tailwind breakpoints
- **I18n Support**: Internationalization for Chinese/English content
- **RBAC Integration**: Role-based UI rendering and access control

## Component Standards
- **TypeScript Props**: Strict interface definitions for all props
- **Error Boundaries**: Graceful error handling for UI components
- **Loading States**: Proper loading and error states for async operations
- **Accessibility**: WCAG compliant components with proper ARIA labels
- **Performance**: Optimize re-renders and bundle size

## Testing
- **Type Checking**: `npm run typecheck` before commits
- **E2E Tests**: Playwright tests in `src/frontend/e2e/`
- **Build Validation**: `npm run build` must pass
- **UX Compliance**: Follow `docs/architecture/frontend-ux-spec.md`

Please work on: $ARGUMENTS

Follow the modular patterns established in existing feature directories.