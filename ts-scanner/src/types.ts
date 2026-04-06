/**
 * Output contract interfaces for the TS scanner.
 *
 * These match the Python scanner's output schema defined in
 * docs/TS_FRONTEND_SPEC.md Section 2. The Python pipeline
 * (formatters, gap_features, investigation_targets) reads
 * these exact shapes via dict key access.
 */

// =============================================================================
// Top-Level Results
// =============================================================================

export interface XRayResults {
  metadata: Metadata;
  summary: Summary;
  structure?: Structure;
  complexity?: Complexity;
  types?: TypeCoverage;
  decorators?: DecoratorInventory;
  async_patterns?: AsyncPatterns;
  // Stubs for Phase 1 signals (empty until implemented)
  side_effects?: SideEffects;
  security_concerns?: Record<string, SecurityConcern[]>;
  silent_failures?: Record<string, SilentFailure[]>;
  sql_strings?: Record<string, SqlString[]>;
  deprecation_markers?: DeprecationMarker[];
  tests?: TestAnalysis;
  hotspots?: Hotspot[];
  imports?: ImportAnalysis;
  calls?: CallAnalysis;
  logic_maps?: LogicMap[];
  cli?: CliAnalysis;
  config_rules?: ConfigRules;
  // TS-specific
  ts_specific?: TsSpecific;
}

// =============================================================================
// Metadata
// =============================================================================

export interface Metadata {
  tool_version: string;
  generated_at: string;
  target_directory: string;
  preset: string | null;
  analysis_options: string[];
  file_count: number;
  language: "typescript" | "javascript" | "mixed";
  parser_tier: "syntax" | "semantic";
  tsconfig_path?: string | null;
}

// =============================================================================
// Summary
// =============================================================================

export interface Summary {
  total_files: number;
  total_lines: number;
  total_tokens: number;
  total_functions: number;
  total_classes: number;
  type_coverage: number;
  total_cc?: number;
  average_cc?: number;
  typed_functions?: number;
}

// =============================================================================
// Structure (skeleton)
// =============================================================================

export interface Structure {
  files: Record<string, FileAnalysis>;
  classes: ClassInfo[];
  functions: FunctionInfo[];
}

export interface FileAnalysis {
  filepath: string;
  line_count: number;
  classes: ClassInfo[];
  functions: FunctionInfo[];
  constants: ConstantInfo[];
  complexity: {
    total_cc: number;
    hotspots: Record<string, number>;
  };
  type_coverage: {
    total_functions: number;
    typed_functions: number;
    coverage_percent: number;
  };
  decorators: Record<string, number>;
  async_patterns: {
    async_functions: number;
    sync_functions: number;
    async_for_loops: number;
    async_context_managers: number;
  };
  // Phase 0: empty arrays, populated in Phase 1
  side_effects: SideEffect[];
  security_concerns: SecurityConcern[];
  silent_failures: SilentFailure[];
  async_violations: AsyncViolation[];
  sql_strings: SqlString[];
  deprecation_markers: DeprecationMarker[];
  env_vars: EnvVar[];
  internal_calls: InternalCall[];
  tokens: {
    original: number;
    skeleton: number;
  };
  parse_error: string | null;
  shared_mutable_state?: SharedMutableState[];
  // TS-specific optional fields
  ts_interfaces?: TsInterfaceInfo[];
  ts_type_aliases?: TsTypeAliasInfo[];
  ts_enums?: TsEnumInfo[];
}

// =============================================================================
// Skeleton sub-types
// =============================================================================

export interface ClassInfo {
  name: string;
  bases: string[];
  methods: MethodInfo[];
  decorators: string[];
  line: number;
  docstring: string | null;
  file?: string;
  kind?: "class" | "interface" | "enum";
  instance_vars?: InstanceVar[];
  state_mutations?: StateMutation[];
}

export interface MethodInfo {
  name: string;
  args: ArgInfo[];
  returns: string | null;
  decorators: string[];
  is_async: boolean;
  line: number;
  complexity: number;
}

export interface FunctionInfo {
  name: string;
  args: ArgInfo[];
  returns: string | null;
  decorators: string[];
  is_async: boolean;
  line: number;
  complexity: number;
  docstring: string | null;
  file?: string;
  is_component?: boolean;
}

export interface ArgInfo {
  name: string;
  type?: string;
  default?: string;
}

export interface ConstantInfo {
  name: string;
  value: string | null;
  line: number;
}

// =============================================================================
// TS-specific structure types
// =============================================================================

export interface TsInterfaceInfo {
  name: string;
  extends: string[];
  members: Array<{ name: string; type: string; optional: boolean }>;
  type_parameters: string[];
  line: number;
  exported: boolean;
}

export interface TsTypeAliasInfo {
  name: string;
  type_kind: "object" | "union" | "intersection" | "mapped" | "conditional" | "primitive" | "other";
  type_parameters: string[];
  line: number;
  exported: boolean;
}

export interface TsEnumInfo {
  name: string;
  members: Array<{ name: string; value: string | number | null }>;
  is_const: boolean;
  line: number;
  exported: boolean;
}

// =============================================================================
// Complexity
// =============================================================================

export interface Complexity {
  hotspots: Hotspot[];
  average_cc: number;
  total_cc: number;
}

export interface Hotspot {
  file: string;
  function: string;
  complexity: number;
}

// =============================================================================
// Type Coverage
// =============================================================================

export interface TypeCoverage {
  coverage: number;
  typed_functions: number;
  total_functions: number;
}

// =============================================================================
// Decorators
// =============================================================================

export interface DecoratorInventory {
  inventory: Record<string, number>;
}

// =============================================================================
// Async Patterns
// =============================================================================

export interface AsyncPatterns {
  async_functions: number;
  sync_functions: number;
  async_for_loops: number;
  async_context_managers: number;
  violations?: AsyncViolation[];
}

// =============================================================================
// Phase 1 stubs (populated later)
// =============================================================================

export interface SideEffects {
  by_type: Record<string, SideEffectEntry[]>;
  by_file: Record<string, SideEffect[]>;
}

export interface SideEffect {
  category: string;
  call: string;
  line: number;
}

export interface SideEffectEntry {
  file: string;
  call: string;
  line: number;
}

export interface SecurityConcern {
  type: string;
  call: string;
  line: number;
  severity: "high" | "medium" | "low";
}

export interface SilentFailure {
  type: string;
  line: number;
  context: string;
}

export interface AsyncViolation {
  file: string;
  function: string;
  violation_type: string;
  call: string;
  line: number;
}

export interface SqlString {
  line: number;
  sql: string;
  context: string;
  type: "query" | "template" | "tagged";
}

export interface DeprecationMarker {
  file: string;
  name: string;
  line: number;
  reason: string | null;
  source: "decorator" | "jsdoc" | "comment";
}

export interface InternalCall {
  call: string;
  line: number;
}

export interface ImportAnalysis {
  graph: Record<string, { imports: string[]; imported_by: string[] }>;
  layers: Record<string, string[]>;
  tiers?: Record<string, string[]>;
  aliases: Record<string, string>;
  alias_patterns: string[];
  orphans: string[];
  circular: string[][];
  external_deps: string[];
  distances: {
    max_depth: number;
    avg_depth: number;
    tightly_coupled: Array<{ modules: string[]; score: number }>;
    hub_modules: Array<{ module: string; connections: number }>;
  };
  summary: {
    total_modules: number;
    internal_edges: number;
    circular_count: number;
    orphan_count: number;
    external_deps_count: number;
  };
}

export interface CallAnalysis {
  cross_module: Record<string, { call_count: number; call_sites: Array<{ file: string; line: number; caller: string }> }>;
  reverse_lookup: Record<string, { caller_count: number; impact_rating: "high" | "medium" | "low"; callers: Array<{ file: string; function: string }> }>;
  most_called: Array<{ function: string; call_sites: number; modules: number }>;
  most_callers: Array<{ function: string; calls_made: number }>;
  isolated_functions: string[];
  high_impact: Array<{ function: string; impact: "high"; callers: number }>;
  summary: {
    total_cross_module_calls: number;
    functions_with_cross_module_callers: number;
    high_impact_functions: number;
    isolated_functions: number;
  };
}

export interface EnvVar {
  variable: string;
  default: string | null;
  fallback_type: "or_fallback" | "nullish_coalesce" | "explicit_default" | "none";
  required: boolean;
  line: number;
}

export interface TestAnalysis {
  test_file_count: number;
  test_function_count: number;
  coverage_by_type: Record<string, number>;
  test_files: Array<{ path: string; tests: number }>;
}

export interface InstanceVar {
  name: string;
  type: string | null;
  visibility: "public" | "private" | "protected";
  has_default: boolean;
  line: number;
}

export interface TsSpecific {
  any_density: {
    explicit_any: number;
    as_any_assertions: number;
    ts_ignore_count: number;
    ts_expect_error_count: number;
  };
  module_system: "esm" | "commonjs" | "mixed";
  declaration_file_count: number;
  module_augmentations: Array<{ target_module: string; file: string; line: number }>;
  namespaces: Array<{ name: string; file: string; line: number; exported: boolean }>;
}

// =============================================================================
// Logic Maps
// =============================================================================

export interface LogicMap {
  method: string;
  file: string;
  line: number;
  complexity: number;
  flow: string[];
  side_effects: string[];
  state_mutations: string[];
  conditions: string[];
  docstring: string | null;
  heuristic: string;
}

// =============================================================================
// Shared Mutable State
// =============================================================================

export interface SharedMutableState {
  name: string;
  kind: "module_variable" | "static_field";
  line: number;
  mutated_by?: string[];
}

export interface StateMutation {
  property: string;
  method: string;
  line: number;
}

// =============================================================================
// CLI Analysis
// =============================================================================

export interface CliAnalysis {
  framework: string | null;
  commands: Array<{ name: string; description: string | null }>;
  options: Array<{ flag: string; description: string | null; type?: string }>;
}

// =============================================================================
// Config Rules
// =============================================================================

export interface ConfigRules {
  typescript: {
    strict: boolean;
    flags: Record<string, boolean | string>;
    config_file: string;
  } | null;
  eslint: { config_file: string; framework: string | null } | null;
  prettier: { config_file: string } | null;
}
