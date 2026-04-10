# TypeScript Scanner: Gap Analysis

Analysis of missing signals, TS-native concepts the scanner doesn't detect, and Python equivalents that have no TS counterpart. This document serves as a roadmap for future scanner improvements.

## Current State

The TS scanner extracts ~30 signal types (interfaces, type aliases, enums, routes, config rules, side effects, security concerns, etc.). The Python scanner extracts ~35. There is significant overlap, but each has unique strengths.

## Tier 1: High-Value Gaps (Framework-Level Analysis)

These are the signals that would most improve deep crawl quality for common TS project types.

### Validation Schema Extraction

| Framework | Pattern | What To Extract | Difficulty |
|-----------|---------|-----------------|-----------|
| **Zod** | `z.object({...})`, `z.string()`, `z.enum([...])` | Schema name, fields, types, constraints, `.refine()` validators | High |
| **class-validator** | `@IsString()`, `@IsEmail()`, `@Min()`, `@Max()` on class fields | DTO class, field constraints, custom validators | High |
| **io-ts** | `t.type({...})`, `t.union([...])` | Codec definitions, composition | High |
| **yup/joi** | `yup.object().shape({...})`, `Joi.object({...})` | Schema fields, validation rules | Medium |

**Why it matters:** Validation schemas define the contract between API boundaries. A deep crawl that can extract "this endpoint expects a body matching `CreateUserSchema` with fields `name: string (3-50 chars), email: email, role: enum(admin,user)`" saves significant investigation time.

**Python equivalent:** Pydantic model extraction (implemented in `gap_features.py` L874-1019) with field constraints, validators, and model hierarchy.

### React Hook Analysis

| Signal | Detection Pattern | Value |
|--------|-------------------|-------|
| Custom hooks | `function use[A-Z].*` or `const use[A-Z].* = ` | Map hook dependency graph |
| Hook rules violations | `useState`/`useEffect` inside conditionals or loops | Bug detection |
| Effect cleanup | `useEffect` returning cleanup function vs. not | Memory leak risk |
| Dependency arrays | `useEffect([...deps])` — stale closure risk | Common bug source |
| Context usage | `createContext` + `useContext` patterns | State architecture |

**Why it matters:** Hooks are the foundation of modern React architecture. Understanding which custom hooks exist, what state they manage, and where dependency arrays may be wrong is essential for any React deep crawl.

**Python equivalent:** None (React is TS/JS-specific).

### NestJS / Angular DI Analysis

| Signal | Detection Pattern | Value |
|--------|-------------------|-------|
| Provider registration | `@Module({ providers: [...] })` | Service wiring map |
| Injectable lifecycle | `@Injectable({ scope: Scope.REQUEST })` | Per-request vs singleton |
| Guard/Interceptor chains | `@UseGuards(...)`, `@UseInterceptors(...)` | Request pipeline |
| Custom decorators | `createParamDecorator(...)` | Hidden behavior |

**Why it matters:** NestJS and Angular rely heavily on DI and decorators. The actual runtime behavior is defined by decorator metadata, not by the code structure visible in the AST. A deep crawl needs to understand the full DI graph.

**Python equivalent:** FastAPI `Depends()` extraction (not implemented).

### ORM Model Extraction

| Framework | Detection Pattern | What To Extract |
|-----------|-------------------|-----------------|
| **Prisma** | `prisma.schema` file, `PrismaClient` usage | Model definitions, relations, indexes |
| **TypeORM** | `@Entity()`, `@Column()`, `@OneToMany()` | Entity fields, relations, migrations |
| **Drizzle** | `pgTable(...)`, `relations(...)` | Table definitions, relation graph |
| **Sequelize** | `Model.init({...})`, `DataTypes.STRING` | Model fields, associations |

**Python equivalent:** SQLAlchemy/Django ORM model extraction (not implemented).

## Tier 2: Medium-Value Gaps

### Middleware Chain Analysis

Currently the scanner detects route registrations but doesn't analyze middleware ordering or dependencies.

| Signal | What To Detect |
|--------|---------------|
| Express `app.use()` ordering | Which middleware runs before which routes |
| Error middleware | `app.use((err, req, res, next) => ...)` — 4-param signature |
| Middleware dependencies | Does auth middleware depend on session middleware? |
| Route-specific middleware | `router.get('/path', authMiddleware, handler)` |

### GraphQL Schema Analysis

| Framework | Detection Pattern |
|-----------|-------------------|
| **type-graphql** | `@ObjectType()`, `@Field()`, `@Resolver()`, `@Query()`, `@Mutation()` |
| **nexus** | `objectType({...})`, `queryField(...)`, `mutationField(...)` |
| **pothos** | `builder.queryType({...})`, `builder.objectType(...)` |
| **SDL-first** | `.graphql` / `.gql` schema files |

### tRPC Router Analysis

| Signal | Detection Pattern |
|--------|-------------------|
| Router definitions | `t.router({...})` |
| Procedure types | `t.procedure.query(...)`, `t.procedure.mutation(...)` |
| Input validation | `.input(z.object({...}))` (Zod integration) |
| Middleware | `t.procedure.use(...)` |

### Barrel File Analysis

Currently not analyzed. Would detect:
- `index.ts` files that are pure re-exports vs. files with logic
- Circular re-export chains
- Namespace barrel patterns (`export * as Foo from './foo'`)
- Tree-shaking impact (does the barrel prevent dead code elimination?)

### Monorepo Workspace Analysis

| Signal | Detection Pattern |
|--------|-------------------|
| Package boundaries | `packages/*/package.json`, `apps/*/package.json` |
| Cross-package imports | `@scope/package-name` imports crossing workspace boundaries |
| Shared type packages | `packages/types/`, `packages/shared/` |
| Build tool config | `nx.json`, `turbo.json`, `lerna.json` task graph |
| Internal dependency graph | Which workspace packages depend on which |

## Tier 3: Lower-Value / Niche Gaps

### TypeScript-Specific Type System Analysis

| Signal | Current Status | What's Missing |
|--------|---------------|----------------|
| Conditional types | Not detected | `T extends U ? X : Y` — affects API flexibility |
| Mapped types | Not detected | `{ [K in keyof T]: ... }` — utility type patterns |
| Template literal types | Not detected | `` `${A}/${B}` `` — route type safety |
| Branded types | Not detected | `type UserId = string & { __brand: 'UserId' }` |
| Discriminated unions | Partially (union type_kind detected) | Missing discriminant field identification |

### Testing Infrastructure

| Signal | Python Status | TS Status |
|--------|--------------|-----------|
| Test setup files | Not analyzed | `setupFilesAfterSetup`, `globalSetup` in vitest/jest config |
| Mock patterns | Not analyzed | `vi.mock()`, `jest.mock()`, `__mocks__/` directories |
| Test factories | Not analyzed | `factory.build()`, fixture patterns |
| E2E test detection | Not analyzed | Playwright, Cypress config files |

### Python-Specific Signals With No TS Equivalent

These Python signals don't have meaningful TS analogues:

| Signal | Why No TS Equivalent |
|--------|---------------------|
| `__all__` export control | TS uses `export` keyword explicitly |
| Metaclass patterns | TS has no metaclasses |
| Generator patterns (`yield`) | TS generators exist but are rarely architectural |
| Context managers (`with`) | TS uses `using` (new) or try/finally |
| Multiple inheritance | TS has single inheritance + interfaces |
| `__init_subclass__` hooks | No TS equivalent |

## Missing Git-Derived Signals (JSON Formatter Gap — Fixed 2026-04-09)

Three Python-side signals have no TS scanner equivalent. The raw data exists in `ts-scanner/src/git-analysis.ts` but isn't synthesized into these higher-level views. All three are best implemented in `xray.py:_augment_with_git()` since they use language-agnostic `git log` parsing.

| Signal | Python source | TS raw data available | Gap |
|--------|--------------|----------------------|-----|
| `author_expertise` | `git_analysis.py` — per-author file ownership profiles | `git.risk[].authors` (count only) | No per-author breakdown or expertise profiling |
| `commit_sizes` | `git_analysis.py:analyze_commit_sizes()` — commit size distribution | `git.velocity[].monthly_commits`, `git.risk[].churn` | No lines-added/removed per commit |
| `priority_files` | Python pipeline aggregation — composite file ranking | `git.risk[].risk_score`, `blast_radius`, `complexity.hotspots` | No cross-signal composite ranking |

**Also noted:** The old `json_formatter.py` allowlist had a `async_violations` entry that matched the Python key but not the TS key (`async_patterns` with violations nested inside). Now moot — the allowlist was replaced with dynamic passthrough that handles all keys from either pipeline.

## Implementation Priority

If implementing these gaps, the recommended order by ROI:

1. **Zod/class-validator schema extraction** — covers the most common validation patterns in modern TS
2. **React hook analysis** — essential for the largest TS ecosystem (React)
3. **NestJS DI analysis** — essential for enterprise TS
4. **Barrel file analysis** — low difficulty, catches circular import issues
5. **ORM model extraction** (Prisma first) — data model understanding
6. **Middleware chain ordering** — request flow understanding
7. **Monorepo workspace analysis** — multi-package project support
8. **GraphQL/tRPC** — growing but more niche

## How These Gaps Affect Deep Crawl Quality

The deep crawl protocols (in `.claude/skills/deep-crawl/SKILL.md`) compensate for scanner gaps via Protocol C grep patterns. An agent can `grep -rn "z.object\|z.string" --include="*.ts"` to find Zod schemas even without scanner support. But:

- **Scanner detection is deterministic** — grep patterns are fragile and miss indirect patterns
- **Scanner data feeds investigation targets** — without scanner detection, these patterns don't appear in `investigation_targets.domain_entities`, so the crawl plan doesn't prioritize them
- **Scanner data feeds the formatter** — xray.md doesn't show validation schemas, so a downstream agent doesn't know they exist without reading files

Each gap closed in the scanner directly improves xray.md quality, which directly improves deep crawl plan quality, which directly improves DEEP_ONBOARD.md quality.
