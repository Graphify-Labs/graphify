import { dirname } from 'node:path';

import { originalPositionFor, TraceMap } from '@jridgewell/trace-mapping';
import type { Node as EstreeNode } from 'estree';
import { walk } from 'estree-walker';
import { parse, VERSION as compilerVersion, type AST } from 'svelte/compiler';
import { svelte2tsx } from 'svelte2tsx';
import ts from 'typescript';

import { structuralNodePolicy, templateNodePolicy } from './schema-policy.js';

const schemaVersion = 2;
const svelte2tsxVersion = '0.7.58';

type Surface = 'module' | 'default' | 'template';
type ScriptLanguage = 'js' | 'ts';

interface BridgeFile {
  id: string;
  path: string;
  source: string;
}

interface BridgeRequest {
  schema_version: number;
  files: BridgeFile[];
}

interface LocatedNode {
  type: string;
  start: number;
  end: number;
  [key: string]: unknown;
}

interface RangeFact {
  start: number;
  end: number;
  start_byte: number;
  end_byte: number;
  line: number;
}

interface BindingIndex {
  idAt(offset: number, name: string): string | null;
}

const emptyBindingIndex: BindingIndex = { idAt: () => null };

function assertNever(value: never): never {
  throw new Error(`unclassified Svelte AST variant: ${JSON.stringify(value)}`);
}

function isLocatedNode(value: unknown): value is LocatedNode {
  return Boolean(
    value
      && typeof value === 'object'
      && typeof (value as { type?: unknown }).type === 'string'
      && typeof (value as { start?: unknown }).start === 'number'
      && typeof (value as { end?: unknown }).end === 'number',
  );
}

function nodeName(value: unknown): string | null {
  if (!value || typeof value !== 'object') return null;
  const node = value as { type?: string; name?: unknown; value?: unknown };
  if (
    (node.type === 'Identifier' || node.type === 'PrivateIdentifier')
    && typeof node.name === 'string'
  ) return node.name;
  if (node.type === 'Literal' && typeof node.value === 'string') return node.value;
  return null;
}

function staticAttribute(script: AST.Script, name: string): string | null {
  const attribute = script.attributes.find(
    (candidate) => candidate.type === 'Attribute' && candidate.name === name,
  );
  if (!attribute || attribute.value === true) return null;
  const parts = Array.isArray(attribute.value) ? attribute.value : [attribute.value];
  if (parts.length !== 1 || parts[0]?.type !== 'Text') return null;
  return parts[0].data;
}

function scriptLanguage(script: AST.Script): ScriptLanguage {
  const language = (staticAttribute(script, 'lang') ?? 'js').toLowerCase();
  return language === 'ts' || language === 'typescript' ? 'ts' : 'js';
}

function lineStarts(source: string): number[] {
  const starts = [0];
  for (let index = 0; index < source.length; index += 1) {
    if (source[index] === '\n') starts.push(index + 1);
  }
  return starts;
}

function offsetAt(starts: number[], line: number, column: number): number | null {
  const start = starts[line - 1];
  return start === undefined ? null : start + column;
}

function sourceRange(
  source: string,
  starts: number[],
  node: { start: number; end: number },
): RangeFact {
  let lineIndex = 0;
  while (lineIndex + 1 < starts.length && (starts[lineIndex + 1] ?? Infinity) <= node.start) {
    lineIndex += 1;
  }
  return {
    start: node.start,
    end: node.end,
    start_byte: Buffer.byteLength(source.slice(0, node.start), 'utf8'),
    end_byte: Buffer.byteLength(source.slice(0, node.end), 'utf8'),
    line: lineIndex + 1,
  };
}

function blankRange(source: string, node: AST.Script | null): string {
  if (!node) return source;
  const blank = source.slice(node.start, node.end).replace(/[^\r\n]/g, ' ');
  return `${source.slice(0, node.start)}${blank}${source.slice(node.end)}`;
}

function compilerOptions(filename: string): ts.CompilerOptions {
  const defaults: ts.CompilerOptions = {
    allowJs: true,
    checkJs: false,
    jsx: ts.JsxEmit.Preserve,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    noEmit: true,
    skipLibCheck: true,
    target: ts.ScriptTarget.ES2022,
  };
  const configPath = ts.findConfigFile(dirname(filename), ts.sys.fileExists, 'tsconfig.json');
  if (!configPath) return defaults;
  const loaded = ts.readConfigFile(configPath, ts.sys.readFile);
  if (loaded.error) return defaults;
  const parsed = ts.parseJsonConfigFileContent(loaded.config, ts.sys, dirname(configPath));
  return { ...defaults, ...parsed.options, noEmit: true };
}

function declarationName(declaration: ts.Declaration): ts.Node {
  if ('name' in declaration && declaration.name) {
    return declaration.name as ts.Node;
  }
  return declaration;
}

function buildBindingIndex(
  source: string,
  filename: string,
  transformedSource: string,
  identitySurface: 'module' | 'instance',
  isTsFile: boolean,
): BindingIndex {
  const transformed = svelte2tsx(transformedSource, {
    filename,
    isTsFile,
    parse,
    version: compilerVersion,
  });
  const virtualFilename = `${filename}.${identitySurface}.tsx`;
  const options = compilerOptions(filename);
  const defaultHost = ts.createCompilerHost(options, true);
  const host: ts.CompilerHost = {
    ...defaultHost,
    fileExists: (path) => path === virtualFilename || defaultHost.fileExists(path),
    readFile: (path) => path === virtualFilename ? transformed.code : defaultHost.readFile(path),
    getSourceFile: (path, languageVersion, onError, shouldCreateNewSourceFile) => {
      if (path === virtualFilename) {
        return ts.createSourceFile(
          path,
          transformed.code,
          languageVersion,
          true,
          ts.ScriptKind.TSX,
        );
      }
      return defaultHost.getSourceFile(
        path,
        languageVersion,
        onError,
        shouldCreateNewSourceFile,
      );
    },
  };
  const program = ts.createProgram([virtualFilename], options, host);
  const generated = program.getSourceFile(virtualFilename);
  if (!generated) return { idAt: () => null };
  const generatedSource = generated;
  const checker = program.getTypeChecker();
  const trace = new TraceMap(transformed.map.toString());
  const starts = lineStarts(source);
  const bindingByOccurrence = new Map<string, string>();

  function originalOffset(node: ts.Node): number | null {
    const location = generatedSource.getLineAndCharacterOfPosition(
      node.getStart(generatedSource),
    );
    const original = originalPositionFor(trace, {
      line: location.line + 1,
      column: location.character,
    });
    if (original.line === null || original.column === null) return null;
    return offsetAt(starts, original.line, original.column);
  }

  function visit(node: ts.Node): void {
    if (ts.isIdentifier(node)) {
      const occurrence = originalOffset(node);
      const symbol = ts.isShorthandPropertyAssignment(node.parent)
        ? (checker.getShorthandAssignmentValueSymbol(node.parent) ?? checker.getSymbolAtLocation(node))
        : checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.[0];
      if (occurrence !== null && declaration) {
        const declarationOffset = originalOffset(declarationName(declaration));
        if (declarationOffset !== null) {
          const bindingId = `${identitySurface}:${declarationOffset}:${symbol.getName()}`;
          bindingByOccurrence.set(`${occurrence}:${node.text}`, bindingId);
        }
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(generatedSource);

  return {
    idAt(offset, name) {
      return bindingByOccurrence.get(`${offset}:${name}`) ?? null;
    },
  };
}

function isCallNamed(node: LocatedNode | null, expected: string): boolean {
  return node?.type === 'CallExpression' && nodeName(node.callee) === expected;
}

function unwrapTypeAnnotation(node: unknown): LocatedNode | null {
  if (!isLocatedNode(node)) return null;
  return node.type === 'TSTypeAnnotation' && isLocatedNode(node.typeAnnotation)
    ? node.typeAnnotation
    : node;
}

interface NamedType {
  name: string;
  identifier: LocatedNode;
}

function namedType(node: unknown): NamedType | null {
  const value = unwrapTypeAnnotation(node);
  if (!value) return null;
  const candidate = value.type === 'TSTypeReference' ? value.typeName : value;
  if (!isLocatedNode(candidate)) return null;
  const name = nodeName(candidate);
  return name ? { name, identifier: candidate } : null;
}

function propertyTypeMap(body: unknown): Map<string, NamedType> {
  const fields = new Map<string, NamedType>();
  if (!Array.isArray(body)) return fields;
  for (const candidate of body) {
    if (!isLocatedNode(candidate) || candidate.type !== 'TSPropertySignature') continue;
    const name = nodeName(candidate.key);
    const valueType = namedType(candidate.typeAnnotation);
    if (name && valueType) fields.set(name, valueType);
  }
  return fields;
}

function typeShapes(program: AST.Script['content']): Map<string, Map<string, NamedType>> {
  const shapes = new Map<string, Map<string, NamedType>>();
  for (const rawStatement of program.body) {
    const statement = rawStatement as unknown as LocatedNode;
    const declaration = statement.type === 'ExportNamedDeclaration'
      ? statement.declaration
      : statement;
    if (!isLocatedNode(declaration)) continue;
    if (declaration.type === 'TSInterfaceDeclaration') {
      const name = nodeName(declaration.id);
      const body = isLocatedNode(declaration.body) ? declaration.body.body : null;
      if (name) shapes.set(name, propertyTypeMap(body));
    } else if (
      declaration.type === 'TSTypeAliasDeclaration'
      && isLocatedNode(declaration.typeAnnotation)
      && declaration.typeAnnotation.type === 'TSTypeLiteral'
    ) {
      const name = nodeName(declaration.id);
      if (name) shapes.set(name, propertyTypeMap(declaration.typeAnnotation.members));
    }
  }
  return shapes;
}

interface ObjectBinding {
  publicName: string;
  localName: string;
  local: LocatedNode;
}

function objectPatternBindings(pattern: LocatedNode): ObjectBinding[] {
  if (pattern.type !== 'ObjectPattern' || !Array.isArray(pattern.properties)) return [];
  const bindings: ObjectBinding[] = [];
  for (const candidate of pattern.properties) {
    if (!isLocatedNode(candidate) || candidate.type !== 'Property') continue;
    const publicName = nodeName(candidate.key);
    let value = candidate.value;
    if (isLocatedNode(value) && value.type === 'AssignmentPattern') value = value.left;
    if (!isLocatedNode(value)) continue;
    const localName = nodeName(value);
    if (publicName && localName) bindings.push({ publicName, localName, local: value });
  }
  return bindings;
}

function asLocated(node: unknown): LocatedNode | null {
  return isLocatedNode(node) ? node : null;
}

function walkEstree(root: unknown, visit: (node: LocatedNode, parent: LocatedNode | null) => void): void {
  walk(root as EstreeNode, {
    enter(rawNode, rawParent) {
      if (isLocatedNode(rawNode)) visit(rawNode, isLocatedNode(rawParent) ? rawParent : null);
    },
  });
}

function extractFileFacts(item: BridgeFile): Record<string, unknown> {
  const { id, path, source } = item;
  const ast = parse(source, { modern: true, filename: path });
  const starts = lineStarts(source);
  const isTsFile = [ast.module, ast.instance].some(
    (script) => script != null && scriptLanguage(script) === 'ts',
  );
  let moduleBindings = emptyBindingIndex;
  let instanceBindings = emptyBindingIndex;
  const semanticDiagnostics: Record<string, unknown>[] = [];
  try {
    if (ast.module) {
      moduleBindings = buildBindingIndex(source, path, source, 'module', isTsFile);
      instanceBindings = buildBindingIndex(
        source,
        path,
        blankRange(source, ast.module),
        'instance',
        isTsFile,
      );
    } else {
      instanceBindings = buildBindingIndex(source, path, source, 'instance', isTsFile);
      moduleBindings = instanceBindings;
    }
  } catch (error) {
    semanticDiagnostics.push({
      code: 'svelte_semantic_unavailable',
      message: `Svelte TypeScript semantic enrichment unavailable: ${
        error instanceof Error ? error.message : String(error)
      }`,
      degraded: true,
    });
  }

  const scripts: Record<string, unknown>[] = [];
  const imports: Record<string, unknown>[] = [];
  const constructions: Record<string, unknown>[] = [];
  const props: Record<string, unknown>[] = [];
  const components: Record<string, unknown>[] = [];
  const templateMembers: Record<string, unknown>[] = [];
  const scriptMembers: Record<string, unknown>[] = [];
  const dynamicImports: Record<string, unknown>[] = [];

  function range(node: { start: number; end: number }): RangeFact {
    return sourceRange(source, starts, node);
  }

  function bindingsFor(surface: Surface): BindingIndex {
    return surface === 'module' ? moduleBindings : instanceBindings;
  }

  function bindingAt(node: unknown, surface: Surface): string | null {
    if (!isLocatedNode(node)) return null;
    const name = nodeName(node);
    if (!name) return null;
    const preferred = bindingsFor(surface).idAt(node.start, name);
    if (preferred || surface !== 'template') return preferred;
    return moduleBindings.idAt(node.start, name);
  }

  function collectDynamicImport(node: LocatedNode, surface: 'script' | 'template'): void {
    let argument: unknown = null;
    if (node.type === 'ImportExpression') argument = node.source;
    if (
      node.type === 'CallExpression'
      && isLocatedNode(node.callee)
      && node.callee.type === 'Import'
      && Array.isArray(node.arguments)
    ) argument = node.arguments[0];
    if (
      isLocatedNode(argument)
      && argument.type === 'Literal'
      && typeof argument.value === 'string'
    ) {
      dynamicImports.push({ source: argument.value, surface, ...range(node) });
    }
  }

  function collectMember(
    node: LocatedNode,
    parent: LocatedNode | null,
    surface: Surface,
    output: Record<string, unknown>[],
  ): void {
    if (node.type === 'CallExpression' && isLocatedNode(node.callee)) {
      const callee = node.callee;
      if (callee.type !== 'MemberExpression' || callee.computed) return;
      const object = asLocated(callee.object);
      const member = nodeName(callee.property);
      const binding = nodeName(object);
      if (object && binding && member) {
        output.push({
          binding,
          binding_id: bindingAt(object, surface),
          member,
          call: true,
          ...range(callee),
        });
      }
      return;
    }
    if (node.type !== 'MemberExpression' || node.computed) return;
    if (parent?.type === 'CallExpression' && parent.callee === node) return;
    const object = asLocated(node.object);
    const member = nodeName(node.property);
    const binding = nodeName(object);
    if (object && binding && member) {
      output.push({
        binding,
        binding_id: bindingAt(object, surface),
        member,
        call: false,
        ...range(node),
      });
    }
  }

  function collectProgram(script: AST.Script | null): void {
    if (!script) return;
    void structuralNodePolicy[script.type];
    const surface = script.context;
    const program = script.content;
    scripts.push({
      context: surface,
      language: scriptLanguage(script),
      ...range(program as unknown as { start: number; end: number }),
    });
    const shapes = typeShapes(program);

    for (const rawStatement of program.body) {
      const statement = rawStatement as unknown as LocatedNode;
      if (statement.type !== 'ImportDeclaration' || !isLocatedNode(statement.source)) continue;
      if (typeof statement.source.value !== 'string' || !Array.isArray(statement.specifiers)) continue;
      for (const rawSpecifier of statement.specifiers) {
        if (!isLocatedNode(rawSpecifier) || !isLocatedNode(rawSpecifier.local)) continue;
        const local = nodeName(rawSpecifier.local);
        if (!local) continue;
        let imported = '*';
        if (rawSpecifier.type === 'ImportDefaultSpecifier') imported = 'default';
        if (rawSpecifier.type === 'ImportSpecifier') imported = nodeName(rawSpecifier.imported) ?? '*';
        imports.push({
          source: statement.source.value,
          local,
          imported,
          binding_id: bindingAt(rawSpecifier.local, surface),
          import_kind: rawSpecifier.importKind ?? statement.importKind ?? 'value',
          context: surface,
          ...range(rawSpecifier),
        });
      }
    }

    walkEstree(program, (node, parent) => {
      collectDynamicImport(node, 'script');
      collectMember(node, parent, surface, scriptMembers);
      if (node.type !== 'VariableDeclarator') return;
      const init = asLocated(node.init);
      const variable = asLocated(node.id);
      if (init?.type === 'NewExpression' && variable) {
        const callee = asLocated(init.callee);
        const binding = nodeName(variable);
        const constructor = nodeName(callee);
        if (binding && constructor && callee) {
          constructions.push({
            binding,
            binding_id: bindingAt(variable, surface),
            constructor,
            constructor_binding_id: bindingAt(callee, surface),
            context: surface,
            ...range(init),
          });
        }
      }
      if (!init || !isCallNamed(init, '$props') || variable?.type !== 'ObjectPattern') return;
      const annotation = unwrapTypeAnnotation(variable.typeAnnotation);
      let fields = new Map<string, NamedType>();
      if (annotation?.type === 'TSTypeLiteral') fields = propertyTypeMap(annotation.members);
      const shape = namedType(annotation);
      if (shape && shapes.has(shape.name)) fields = shapes.get(shape.name) ?? fields;
      for (const objectBinding of objectPatternBindings(variable)) {
        const fieldType = fields.get(objectBinding.publicName) ?? null;
        props.push({
          public: objectBinding.publicName,
          binding: objectBinding.localName,
          binding_id: bindingAt(objectBinding.local, surface),
          type_name: fieldType?.name ?? null,
          type_binding_id: fieldType ? bindingAt(fieldType.identifier, surface) : null,
          legacy: false,
          context: surface,
          ...range(node),
        });
      }
    });

    for (const rawStatement of program.body) {
      const statement = rawStatement as unknown as LocatedNode;
      if (statement.type !== 'ExportNamedDeclaration') continue;
      const declaration = asLocated(statement.declaration);
      if (declaration?.type !== 'VariableDeclaration' || declaration.kind !== 'let') continue;
      if (!Array.isArray(declaration.declarations)) continue;
      for (const rawEntry of declaration.declarations) {
        if (!isLocatedNode(rawEntry) || !isLocatedNode(rawEntry.id)) continue;
        const binding = nodeName(rawEntry.id);
        if (!binding) continue;
        const type = namedType(rawEntry.id.typeAnnotation);
        props.push({
          public: binding,
          binding,
          binding_id: bindingAt(rawEntry.id, surface),
          type_name: type?.name ?? null,
          type_binding_id: type ? bindingAt(type.identifier, surface) : null,
          legacy: true,
          context: surface,
          ...range(rawEntry),
        });
      }
    }
  }

  function componentProps(
    node: AST.Component | AST.SvelteComponent,
  ): Record<string, unknown>[] {
    const values: Record<string, unknown>[] = [];
    for (const attribute of node.attributes) {
      if (attribute.type !== 'Attribute') continue;
      if (attribute.value === true) continue;
      const parts = Array.isArray(attribute.value) ? attribute.value : [attribute.value];
      if (parts.length !== 1 || parts[0]?.type !== 'ExpressionTag') continue;
      const expression = parts[0].expression as unknown as LocatedNode;
      const binding = nodeName(expression);
      if (binding) {
        values.push({
          prop: attribute.name,
          binding,
          binding_id: bindingAt(expression, 'template'),
          ...range(attribute),
        });
      }
    }
    return values;
  }

  function collectComponent(node: AST.Component): void {
    const local = node.name.split('.', 1)[0] ?? node.name;
    components.push({
      name: node.name,
      local,
      binding_id: instanceBindings.idAt(node.start + 1, local)
        ?? moduleBindings.idAt(node.start + 1, local),
      props: componentProps(node),
      ...range(node),
    });
  }

  function collectLegacyDynamicComponent(node: AST.SvelteComponent): void {
    const expression = node.expression as unknown as LocatedNode;
    const local = nodeName(expression);
    if (!local) return;
    components.push({
      name: 'svelte:component',
      local,
      binding_id: bindingAt(expression, 'template'),
      props: componentProps(node),
      ...range(node),
    });
  }

  function visitDirective(directive: AST.Directive): void {
    switch (directive.type) {
      case 'AnimateDirective':
      case 'BindDirective':
      case 'ClassDirective':
      case 'LetDirective':
      case 'OnDirective':
      case 'StyleDirective':
      case 'TransitionDirective':
      case 'UseDirective':
        return;
      default:
        assertNever(directive);
    }
  }

  function visitElement(element: AST.ElementLike): void {
    for (const attribute of element.attributes) visitTemplateNode(attribute);
    visitFragment(element.fragment);
  }

  function visitTemplateNode(node: AST.TemplateNode): void {
    const schemaPolicy = templateNodePolicy[node.type];
    switch (node.type) {
      case 'Root':
        visitFragment(node.fragment);
        return;
      case 'Component':
        collectComponent(node);
        visitElement(node);
        return;
      case 'TitleElement':
      case 'SlotElement':
      case 'RegularElement':
      case 'SvelteBody':
      case 'SvelteBoundary':
      case 'SvelteDocument':
      case 'SvelteElement':
      case 'SvelteFragment':
      case 'SvelteHead':
      case 'SvelteSelf':
      case 'SvelteWindow':
        visitElement(node);
        return;
      case 'SvelteOptions':
        if (schemaPolicy !== 'intermediate') {
          throw new Error('SvelteOptions must remain classified as intermediate');
        }
        return;
      case 'SvelteComponent':
        collectLegacyDynamicComponent(node);
        visitElement(node);
        return;
      case 'EachBlock':
        visitFragment(node.body);
        if (node.fallback) visitFragment(node.fallback);
        return;
      case 'IfBlock':
        visitFragment(node.consequent);
        if (node.alternate) visitFragment(node.alternate);
        return;
      case 'AwaitBlock':
        if (node.pending) visitFragment(node.pending);
        if (node.then) visitFragment(node.then);
        if (node.catch) visitFragment(node.catch);
        return;
      case 'KeyBlock':
        visitFragment(node.fragment);
        return;
      case 'SnippetBlock':
        visitFragment(node.body);
        return;
      case 'AnimateDirective':
      case 'BindDirective':
      case 'ClassDirective':
      case 'LetDirective':
      case 'OnDirective':
      case 'StyleDirective':
      case 'TransitionDirective':
      case 'UseDirective':
        visitDirective(node);
        return;
      case 'Attribute':
      case 'SpreadAttribute':
      case 'AttachTag':
      case 'ConstTag':
      case 'DeclarationTag':
      case 'DebugTag':
      case 'ExpressionTag':
      case 'HtmlTag':
      case 'RenderTag':
      case 'Text':
      case 'Comment':
        return;
      default:
        assertNever(node);
    }
  }

  function visitFragment(fragment: AST.Fragment): void {
    void structuralNodePolicy[fragment.type];
    for (const node of fragment.nodes) visitTemplateNode(node);
  }

  collectProgram(ast.module);
  collectProgram(ast.instance);
  visitTemplateNode(ast);

  // Expression-site completeness comes from this single compiler-AST walk.
  // It begins at the fragment, so script programs are never double-processed.
  walkEstree(ast.fragment, (node, parent) => {
    collectDynamicImport(node, 'template');
    collectMember(node, parent, 'template', templateMembers);
  });

  function dedupe(facts: Record<string, unknown>[], key: (fact: Record<string, unknown>) => string) {
    const seen = new Set<string>();
    return facts.filter((fact) => {
      const value = key(fact);
      if (seen.has(value)) return false;
      seen.add(value);
      return true;
    });
  }

  return {
    id,
    scripts,
    imports,
    constructions,
    props,
    components,
    template_members: dedupe(
      templateMembers,
      (fact) => `${fact.start}:${fact.binding_id}:${fact.member}:${fact.call}`,
    ),
    script_members: dedupe(
      scriptMembers,
      (fact) => `${fact.start}:${fact.binding_id}:${fact.member}:${fact.call}`,
    ),
    dynamic_imports: dedupe(
      dynamicImports,
      (fact) => `${fact.start}:${fact.source}:${fact.surface}`,
    ),
    diagnostics: semanticDiagnostics,
  };
}

async function main(): Promise<void> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(Buffer.from(chunk));
  const request = JSON.parse(Buffer.concat(chunks).toString('utf8')) as BridgeRequest;
  if (request.schema_version !== schemaVersion || !Array.isArray(request.files)) {
    throw new Error(`unsupported Svelte AST bridge schema: ${request.schema_version}`);
  }
  const files = request.files.map((item) => {
    try {
      return extractFileFacts(item);
    } catch (error) {
      const compilerError = error as Error & { code?: string; position?: [number, number] };
      return {
        id: item.id,
        diagnostics: [{
          code: compilerError.code ?? 'svelte_parse_error',
          message: error instanceof Error ? error.message : String(error),
          start: compilerError.position?.[0] ?? null,
          end: compilerError.position?.[1] ?? null,
        }],
      };
    }
  });
  process.stdout.write(JSON.stringify({
    schema_version: schemaVersion,
    compiler_version: compilerVersion,
    svelte2tsx_version: svelte2tsxVersion,
    typescript_version: ts.version,
    files,
  }));
}

main().catch((error: unknown) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exitCode = 1;
});
