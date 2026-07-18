import type { AST } from 'svelte/compiler';

export type SchemaPolicy = 'fixture' | 'intermediate';

/**
 * Compiler-schema contract for every public author template discriminant.
 *
 * `satisfies Record<...>` is intentional: a pinned Svelte upgrade that adds or
 * removes a union member must fail typecheck here before the bridge can build.
 * The corpus imports this exact object, so changing a classification also has
 * immediate fixture consequences.
 */
export const templateNodePolicy = {
  Root: 'fixture',
  Text: 'fixture',
  ExpressionTag: 'fixture',
  HtmlTag: 'fixture',
  Comment: 'fixture',
  ConstTag: 'fixture',
  DeclarationTag: 'fixture',
  DebugTag: 'fixture',
  RenderTag: 'fixture',
  AttachTag: 'fixture',
  AnimateDirective: 'fixture',
  BindDirective: 'fixture',
  ClassDirective: 'fixture',
  LetDirective: 'fixture',
  OnDirective: 'fixture',
  StyleDirective: 'fixture',
  TransitionDirective: 'fixture',
  UseDirective: 'fixture',
  Component: 'fixture',
  TitleElement: 'fixture',
  SlotElement: 'fixture',
  RegularElement: 'fixture',
  SvelteBody: 'fixture',
  SvelteBoundary: 'fixture',
  SvelteComponent: 'fixture',
  SvelteDocument: 'fixture',
  SvelteElement: 'fixture',
  SvelteFragment: 'fixture',
  SvelteHead: 'fixture',
  SvelteOptions: 'intermediate',
  SvelteSelf: 'fixture',
  SvelteWindow: 'fixture',
  EachBlock: 'fixture',
  IfBlock: 'fixture',
  AwaitBlock: 'fixture',
  KeyBlock: 'fixture',
  SnippetBlock: 'fixture',
  Attribute: 'fixture',
  SpreadAttribute: 'fixture',
} as const satisfies Record<AST.TemplateNode['type'], SchemaPolicy>;

type StructuralAuthorNode = AST.Fragment | AST.Script;

/** Structural author nodes deliberately outside `AST.TemplateNode`. */
export const structuralNodePolicy = {
  Fragment: 'fixture',
  Script: 'fixture',
} as const satisfies Record<StructuralAuthorNode['type'], SchemaPolicy>;
