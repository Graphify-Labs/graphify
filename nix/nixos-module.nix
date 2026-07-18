{
  config,
  graphifyPackage ? null,
  lib,
  pkgs,
  ...
}: let
  inherit (lib) concatLists escapeShellArgs filterAttrs flatten mapAttrs' mapAttrsToList mkEnableOption mkIf mkMerge mkOption nameValuePair optional optionalAttrs optionalString types unique;
  cfg = config.services.graphify;

  builtInBackends = [
    "azure"
    "bedrock"
    "claude"
    "claude-cli"
    "acp"
    "codex-cli"
    "deepseek"
    "gemini"
    "kimi"
    "ollama"
    "openai"
  ];

  backendApiKeyVariables = {
    azure = "AZURE_OPENAI_API_KEY";
    claude = "ANTHROPIC_API_KEY";
    deepseek = "DEEPSEEK_API_KEY";
    gemini = "GEMINI_API_KEY";
    kimi = "MOONSHOT_API_KEY";
    ollama = "OLLAMA_API_KEY";
    openai = "OPENAI_API_KEY";
  };

  backendBaseUrlVariables = {
    azure = "AZURE_OPENAI_ENDPOINT";
    claude = "ANTHROPIC_BASE_URL";
    deepseek = "DEEPSEEK_BASE_URL";
    gemini = "GEMINI_BASE_URL";
    kimi = "KIMI_BASE_URL";
    ollama = "OLLAMA_BASE_URL";
    openai = "OPENAI_BASE_URL";
  };

  positiveInt = types.ints.positive;
  nullablePositiveInt = types.nullOr positiveInt;
  nullablePositiveNumber = types.nullOr (types.addCheck types.number (value: value > 0));

  postgresOptions = {name, ...}: {
    options = {
      enable = mkEnableOption "PostgreSQL schema introspection for ${name}";

      host = mkOption {
        type = types.str;
        default = "/run/postgresql";
        description = "libpq host name, address, or Unix socket directory.";
      };

      port = mkOption {
        type = types.port;
        default = 5432;
        description = "PostgreSQL port.";
      };

      database = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Database whose schema Graphify introspects.";
      };

      user = mkOption {
        type = types.str;
        default = cfg.user;
        defaultText = lib.literalExpression "config.services.graphify.user";
        description = "PostgreSQL role. Local peer authentication can use the Graphify system user.";
      };

      sslMode = mkOption {
        type = types.enum ["disable" "allow" "prefer" "require" "verify-ca" "verify-full"];
        default = "prefer";
        description = "libpq SSL mode.";
      };

      pgpassFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Optional pgpass file loaded as a systemd credential; it never appears on argv.";
      };

      systemdService = mkOption {
        type = types.nullOr types.str;
        default = null;
        example = "postgresql.service";
        description = "Optional local PostgreSQL unit required before extraction.";
      };
    };
  };

  extractionOptions = {name, ...}: {
    options = {
      enable = mkEnableOption "headless extraction for ${name}" // {default = true;};
      startAtBoot = mkOption {
        type = types.bool;
        default = true;
        description = "Run extraction during multi-user startup.";
      };
      onCalendar = mkOption {
        type = types.nullOr types.str;
        default = null;
        example = "daily";
        description = "Optional systemd calendar schedule.";
      };
      mode = mkOption {
        type = types.enum ["normal" "deep"];
        default = "normal";
        description = "Semantic extraction depth.";
      };
      codeOnly = mkOption {
        type = types.bool;
        default = false;
      };
      noCluster = mkOption {
        type = types.bool;
        default = false;
      };
      dedup = mkOption {
        type = types.bool;
        default = false;
      };
      googleWorkspace = mkOption {
        type = types.bool;
        default = false;
      };
      global = mkOption {
        type = types.bool;
        default = false;
      };
      tag = mkOption {
        type = types.nullOr types.str;
        default = null;
      };
      maxWorkers = mkOption {
        type = nullablePositiveInt;
        default = null;
      };
      tokenBudget = mkOption {
        type = nullablePositiveInt;
        default = null;
      };
      maxConcurrency = mkOption {
        type = nullablePositiveInt;
        default = null;
      };
      apiTimeout = mkOption {
        type = nullablePositiveNumber;
        default = null;
      };
      resolution = mkOption {
        type = types.addCheck types.number (value: value > 0);
        default = 1.0;
      };
      excludeHubs = mkOption {
        type = types.nullOr types.number;
        default = null;
      };
      excludes = mkOption {
        type = types.listOf types.str;
        default = [];
      };
      timing = mkOption {
        type = types.bool;
        default = false;
      };
    };
  };

  llmOptions = {name, ...}: {
    options = {
      backend = mkOption {
        type = types.nullOr types.str;
        default = null;
        example = "openai";
        description = "Built-in or custom Graphify backend name.";
      };
      customProvider = mkOption {
        type = types.bool;
        default = false;
        description = "Whether backend names an entry from providersFile instead of a built-in backend.";
      };
      model = mkOption {
        type = types.nullOr types.str;
        default = null;
      };
      baseUrl = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Built-in provider endpoint override.";
      };
      apiKeyFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Provider API key loaded through a systemd credential.";
      };
      apiKeyEnvironmentVariable = mkOption {
        type = types.nullOr (types.addCheck types.str (value: builtins.match "[A-Z_][A-Z0-9_]*" value != null));
        default = null;
        example = "OPENAI_API_KEY";
        description = "Explicit key variable for a custom provider or non-default alias.";
      };
      providersFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Custom providers.json mounted read-only at HOME/.graphify/providers.json.";
      };
      acp = mkOption {
        type = types.submodule {
          options = {
            binary = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "ACP provider command. Defaults to codex-acp on PATH.";
            };
            args = mkOption {
              type = types.listOf types.str;
              default = [];
              description = "ACP adapter arguments encoded as JSON for the client.";
            };
            configOptions = mkOption {
              type = types.attrsOf types.str;
              default = {mode = "read-only";};
              description = "ACP session configuration options applied after session/new.";
            };
          };
        };
        default = {};
      };
    };
  };

  serverOptions = {name, ...}: {
    options = {
      enable = mkEnableOption "HTTP MCP serving for ${name}";
      host = mkOption {
        type = types.str;
        default = "127.0.0.1";
      };
      port = mkOption {
        type = types.port;
        default = 8080;
      };
      path = mkOption {
        type = types.str;
        default = "/mcp";
      };
      jsonResponse = mkOption {
        type = types.bool;
        default = false;
      };
      stateless = mkOption {
        type = types.bool;
        default = false;
      };
      sessionTimeout = mkOption {
        type = types.addCheck types.number (value: value >= 0);
        default = 3600;
      };
      apiKeyFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "MCP bearer key loaded through a systemd credential.";
      };
      unsafeAllowUnauthenticated = mkOption {
        type = types.bool;
        default = false;
        description = "Explicitly allow an unauthenticated non-loopback listener.";
      };
      openFirewall = mkOption {
        type = types.bool;
        default = false;
      };
    };
  };

  sinkOptions = sink: {name, ...}: {
    options = {
      enable = mkEnableOption "${sink} export for ${name}";
      uri = mkOption {
        type = types.nullOr types.str;
        default = null;
        example =
          if sink == "neo4j"
          then "bolt://127.0.0.1:7687"
          else "falkordb://127.0.0.1:6379";
        description = "Graph database URI passed to Graphify's push exporter.";
      };
      user = mkOption {
        type = types.nullOr types.str;
        default =
          if sink == "neo4j"
          then "neo4j"
          else null;
        description = "Optional graph database user.";
      };
      passwordFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Password loaded through a systemd credential and provider-specific environment variable.";
      };
      onExtraction = mkOption {
        type = types.bool;
        default = true;
        description = "Push after each successful extraction.";
      };
      onCalendar = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Optional independent systemd calendar schedule.";
      };
    };
  };

  instanceOptions = {name, ...}: {
    options = {
      stateDirectory = mkOption {
        type = types.str;
        default = "/var/lib/graphify/${name}";
        description = "Mutable extraction state; graph.json is stored below graphify-out/.";
      };

      source = {
        path = mkOption {
          type = types.nullOr types.str;
          default = null;
          description = "Optional absolute runtime corpus path.";
        };
        cargo = mkOption {
          type = types.bool;
          default = false;
        };
        postgresql = mkOption {
          type = types.submodule postgresOptions;
          default = {};
        };
      };

      extraction = mkOption {
        type = types.submodule extractionOptions;
        default = {};
      };
      llm = mkOption {
        type = types.submodule llmOptions;
        default = {};
      };

      watch = {
        enable = mkEnableOption "filesystem watching for ${name}";
        debounce = mkOption {
          type = types.addCheck types.number (value: value > 0);
          default = 3.0;
        };
      };

      server = mkOption {
        type = types.submodule serverOptions;
        default = {};
      };

      exports = {
        neo4j = mkOption {
          type = types.submodule (sinkOptions "neo4j");
          default = {};
        };
        falkordb = mkOption {
          type = types.submodule (sinkOptions "falkordb");
          default = {};
        };
      };

      environment = mkOption {
        type = types.attrsOf types.str;
        default = {};
        description = "Additional non-secret Graphify/provider environment variables.";
      };

      environmentFiles = mkOption {
        type = types.listOf types.path;
        default = [];
        description = "Systemd environment files for provider/AWS/runtime settings and secrets.";
      };

      runtimePackages = mkOption {
        type = types.listOf types.package;
        default = [];
        example = lib.literalExpression "[ pkgs.claude-code pkgs.gws ]";
        description = "External executables added to service PATH, such as claude, codex-acp, or gws.";
      };
    };
  };

  enabledInstances = cfg.instances;

  graphOut = instance: "${instance.stateDirectory}/graphify-out";
  graphPath = instance: "${graphOut instance}/graph.json";

  llmKeyVariable = instance:
    if instance.llm.apiKeyEnvironmentVariable != null
    then instance.llm.apiKeyEnvironmentVariable
    else if instance.llm.backend != null
    then backendApiKeyVariables.${instance.llm.backend} or null
    else null;

  baseEnvironment = instance: let
    pg = instance.source.postgresql;
    backend = instance.llm.backend;
    acpBackend = backend == "acp";
    baseUrlVariable =
      if backend != null
      then backendBaseUrlVariables.${backend} or null
      else null;
  in
    {
      HOME = instance.stateDirectory;
      PYTHONDONTWRITEBYTECODE = "1";
    }
    // optionalAttrs pg.enable {
      PGHOST = pg.host;
      PGPORT = toString pg.port;
      PGDATABASE = pg.database;
      PGUSER = pg.user;
      PGSSLMODE = pg.sslMode;
    }
    // optionalAttrs (instance.llm.baseUrl != null && baseUrlVariable != null) {
      ${baseUrlVariable} = instance.llm.baseUrl;
    }
    // optionalAttrs acpBackend ({
      GRAPHIFY_ACP_ARGS_JSON = builtins.toJSON instance.llm.acp.args;
      GRAPHIFY_ACP_CONFIG_JSON = builtins.toJSON instance.llm.acp.configOptions;
      GRAPHIFY_ACP_MODEL = if instance.llm.model != null then instance.llm.model else "";
    } // optionalAttrs (instance.llm.acp.binary != null) {
      GRAPHIFY_ACP_BIN = instance.llm.acp.binary;
    })
    // instance.environment;

  extractionArguments = name: instance:
    ["extract"]
    ++ optional (instance.source.path != null) instance.source.path
    ++ optional (instance.llm.backend != null) "--backend=${instance.llm.backend}"
    ++ optional (instance.llm.model != null) "--model=${instance.llm.model}"
    ++ optional (instance.extraction.mode == "deep") "--mode=deep"
    ++ ["--out=${instance.stateDirectory}"]
    ++ optional instance.extraction.noCluster "--no-cluster"
    ++ optional instance.extraction.dedup "--dedup-llm"
    ++ optional instance.extraction.codeOnly "--code-only"
    ++ optional instance.extraction.googleWorkspace "--google-workspace"
    ++ optional instance.extraction.global "--global"
    ++ optional (instance.extraction.tag != null) "--as=${instance.extraction.tag}"
    ++ optional (instance.extraction.maxWorkers != null) "--max-workers=${toString instance.extraction.maxWorkers}"
    ++ optional (instance.extraction.tokenBudget != null) "--token-budget=${toString instance.extraction.tokenBudget}"
    ++ optional (instance.extraction.maxConcurrency != null) "--max-concurrency=${toString instance.extraction.maxConcurrency}"
    ++ optional (instance.extraction.apiTimeout != null) "--api-timeout=${toString instance.extraction.apiTimeout}"
    ++ ["--resolution=${toString instance.extraction.resolution}"]
    ++ optional (instance.extraction.excludeHubs != null) "--exclude-hubs=${toString instance.extraction.excludeHubs}"
    ++ flatten (map (value: ["--exclude" value]) instance.extraction.excludes)
    ++ optional instance.source.postgresql.enable "--postgres="
    ++ optional instance.source.cargo "--cargo"
    ++ optional instance.extraction.timing "--timing";

  credentialSetup = instance: let
    keyVariable = llmKeyVariable instance;
  in ''
    ${optionalString (instance.source.postgresql.pgpassFile != null) ''
      export PGPASSFILE="$CREDENTIALS_DIRECTORY/postgresql-pgpass"
    ''}
    ${optionalString (instance.llm.apiKeyFile != null && keyVariable != null) ''
      export ${keyVariable}="$(${pkgs.coreutils}/bin/cat "$CREDENTIALS_DIRECTORY/llm-api-key")"
    ''}
  '';

  extractionScript = name: instance:
    pkgs.writeShellScript "graphify-${name}-extract" ''
      set -eu
      ${credentialSetup instance}
      exec ${lib.getExe cfg.package} ${escapeShellArgs (extractionArguments name instance)}
    '';

  serverScript = name: instance:
    pkgs.writeShellScript "graphify-${name}-mcp" ''
      set -eu
      ${optionalString (instance.server.apiKeyFile != null) ''
        export GRAPHIFY_API_KEY="$(${pkgs.coreutils}/bin/cat "$CREDENTIALS_DIRECTORY/mcp-api-key")"
      ''}
      exec ${cfg.package}/bin/graphify-mcp ${escapeShellArgs ([
          (graphPath instance)
          "--transport=http"
          "--host=${instance.server.host}"
          "--port=${toString instance.server.port}"
          "--path=${instance.server.path}"
          "--session-timeout=${toString instance.server.sessionTimeout}"
        ]
        ++ optional instance.server.jsonResponse "--json-response"
        ++ optional instance.server.stateless "--stateless")}
    '';

  exportScript = name: instance: sink: sinkCfg: let
    passwordVariable =
      if sink == "neo4j"
      then "NEO4J_PASSWORD"
      else "FALKORDB_PASSWORD";
  in
    pkgs.writeShellScript "graphify-${name}-${sink}-export" ''
      set -eu
      ${optionalString (sinkCfg.passwordFile != null) ''
        export ${passwordVariable}="$(${pkgs.coreutils}/bin/cat "$CREDENTIALS_DIRECTORY/graph-database-password")"
      ''}
      exec ${lib.getExe cfg.package} ${escapeShellArgs ([
          "export"
          sink
          "--graph"
          (graphPath instance)
          "--push"
          sinkCfg.uri
        ]
        ++ optional (sinkCfg.user != null) "--user=${sinkCfg.user}")}
    '';

  commonServiceConfig = instance: {
    User = cfg.user;
    Group = cfg.group;
    UMask = "0077";
    NoNewPrivileges = true;
    PrivateTmp = true;
    ProtectSystem = "strict";
    ProtectHome = "read-only";
    ReadWritePaths = [instance.stateDirectory];
    ReadOnlyPaths = optional (instance.source.path != null) instance.source.path;
    EnvironmentFile = map toString instance.environmentFiles;
  };

  instanceAssertions = concatLists (mapAttrsToList (name: instance: let
    pg = instance.source.postgresql;
    server = instance.server;
    loopback = builtins.elem server.host ["127.0.0.1" "::1" "localhost"];
    keyVariable = llmKeyVariable instance;
    sinkAssertions = concatLists (mapAttrsToList (sink: sinkCfg: [
        {
          assertion = !sinkCfg.enable || sinkCfg.uri != null;
          message = "services.graphify.instances.${name}.exports.${sink}.uri is required when the sink is enabled.";
        }
        {
          assertion = !sinkCfg.enable || !sinkCfg.onExtraction || instance.extraction.enable;
          message = "services.graphify.instances.${name}.exports.${sink}.onExtraction requires extraction.enable.";
        }
        {
          assertion = sink != "neo4j" || !sinkCfg.enable || sinkCfg.passwordFile != null;
          message = "services.graphify.instances.${name}.exports.neo4j.passwordFile is required by Neo4j push.";
        }
      ])
      instance.exports);
  in
    [
      {
        assertion = !instance.extraction.enable || instance.source.path != null || pg.enable;
        message = "services.graphify.instances.${name} needs source.path and/or source.postgresql.enable when extraction is enabled.";
      }
      {
        assertion = !pg.enable || pg.database != null;
        message = "services.graphify.instances.${name}.source.postgresql.database is required when PostgreSQL introspection is enabled.";
      }
      {
        assertion = !instance.source.cargo || instance.source.path != null;
        message = "services.graphify.instances.${name}.source.cargo requires source.path.";
      }
      {
        assertion = !instance.watch.enable || instance.source.path != null;
        message = "services.graphify.instances.${name}.watch.enable requires source.path.";
      }
      {
        assertion = !instance.watch.enable || instance.extraction.enable;
        message = "services.graphify.instances.${name}.watch.enable requires extraction.enable for the initial graph.";
      }
      {
        assertion = lib.hasPrefix "/" instance.stateDirectory;
        message = "services.graphify.instances.${name}.stateDirectory must be absolute.";
      }
      {
        assertion = instance.source.path == null || lib.hasPrefix "/" instance.source.path;
        message = "services.graphify.instances.${name}.source.path must be absolute.";
      }
      {
        assertion = !(instance.environment ? GRAPHIFY_OUT) && !(instance.environment ? HOME);
        message = "services.graphify.instances.${name}.environment must not override module-owned GRAPHIFY_OUT or HOME paths.";
      }
      {
        assertion = !server.enable || lib.hasPrefix "/" server.path;
        message = "services.graphify.instances.${name}.server.path must begin with '/'.";
      }
      {
        assertion = !server.enable || loopback || server.apiKeyFile != null || server.unsafeAllowUnauthenticated;
        message = "services.graphify.instances.${name} refuses unauthenticated non-loopback MCP; set server.apiKeyFile or unsafeAllowUnauthenticated.";
      }
      {
        assertion = instance.llm.backend == null || instance.llm.customProvider || builtins.elem instance.llm.backend builtInBackends;
        message = "services.graphify.instances.${name}.llm.backend is not built in; set llm.customProvider for providersFile entries.";
      }
      {
        assertion = !instance.llm.customProvider || instance.llm.providersFile != null;
        message = "services.graphify.instances.${name}.llm.customProvider requires llm.providersFile.";
      }
      {
        assertion = instance.llm.apiKeyFile == null || keyVariable != null;
        message = "services.graphify.instances.${name}.llm.apiKeyFile requires a known backend or apiKeyEnvironmentVariable.";
      }
    ]
    ++ sinkAssertions)
  enabledInstances);
in {
  options.services.graphify = {
    enable = mkEnableOption "Graphify extraction and MCP services";

    package = mkOption {
      type = types.nullOr types.package;
      default = graphifyPackage;
      defaultText = lib.literalExpression "graphify.packages.<system>.full";
      description = "Graphify package. The upstream module supplies the full runtime package.";
    };

    user = mkOption {
      type = types.str;
      default = "graphify";
    };
    group = mkOption {
      type = types.str;
      default = "graphify";
    };
    instances = mkOption {
      type = types.attrsOf (types.submodule instanceOptions);
      default = {};
      description = "Named Graphify graphs with independent sources, state, schedules, and MCP listeners.";
    };
  };

  config = mkIf cfg.enable (mkMerge [
    {
      assertions =
        [
          {
            assertion = cfg.package != null;
            message = "services.graphify.package must be set when Graphify is enabled.";
          }
          {
            assertion = cfg.instances != {};
            message = "services.graphify.instances must contain at least one instance.";
          }
        ]
        ++ instanceAssertions;

      users.groups.${cfg.group} = {};
      users.users.${cfg.user} = {
        isSystemUser = true;
        group = cfg.group;
        home = "/var/lib/graphify";
        createHome = true;
      };

      systemd.tmpfiles.rules = flatten (mapAttrsToList (_: instance: [
          "d ${instance.stateDirectory} 0750 ${cfg.user} ${cfg.group} - -"
          "d ${instance.stateDirectory}/.graphify 0750 ${cfg.user} ${cfg.group} - -"
        ])
        enabledInstances);

      networking.firewall.allowedTCPPorts =
        unique (mapAttrsToList (_: instance: instance.server.port)
          (filterAttrs (_: instance: instance.server.enable && instance.server.openFirewall) enabledInstances));
    }

    {
      systemd.services = mkMerge (mapAttrsToList (name: instance: let
        extractUnit = "graphify-${name}-extract";
        pgService = instance.source.postgresql.systemdService;
        providerBind =
          optional (instance.llm.providersFile != null)
          "${toString instance.llm.providersFile}:${instance.stateDirectory}/.graphify/providers.json";
      in
        mkMerge ([
            (mkIf instance.extraction.enable {
              ${extractUnit} = {
                description = "Extract Graphify graph ${name}";
                wantedBy = optional instance.extraction.startAtBoot "multi-user.target";
                after = optional (pgService != null) pgService;
                requires = optional (pgService != null) pgService;
                environment = baseEnvironment instance;
                path = instance.runtimePackages;
                unitConfig.OnSuccess =
                  mapAttrsToList
                  (sink: _: "graphify-${name}-${sink}.service")
                  (filterAttrs (_: sinkCfg: sinkCfg.enable && sinkCfg.onExtraction) instance.exports);
                serviceConfig =
                  commonServiceConfig instance
                  // {
                    Type = "oneshot";
                    ExecStart = extractionScript name instance;
                    LoadCredential =
                      optional (instance.source.postgresql.pgpassFile != null) "postgresql-pgpass:${toString instance.source.postgresql.pgpassFile}"
                      ++ optional (instance.llm.apiKeyFile != null) "llm-api-key:${toString instance.llm.apiKeyFile}";
                    BindReadOnlyPaths = providerBind;
                  };
              };
            })
            (mkIf instance.watch.enable {
              "graphify-${name}-watch" = {
                description = "Watch Graphify corpus ${name}";
                wantedBy = ["multi-user.target"];
                after = ["${extractUnit}.service"];
                environment = baseEnvironment instance // {GRAPHIFY_OUT = graphOut instance;};
                path = instance.runtimePackages;
                serviceConfig =
                  commonServiceConfig instance
                  // {
                    ExecStart = "${lib.getExe cfg.package} watch ${lib.escapeShellArg instance.source.path} --debounce ${toString instance.watch.debounce}";
                    Restart = "on-failure";
                    RestartSec = "5s";
                  };
              };
            })
            (mkIf instance.server.enable {
              "graphify-${name}" = {
                description = "Graphify MCP server ${name}";
                wantedBy = ["multi-user.target"];
                after = optional instance.extraction.enable "${extractUnit}.service";
                environment = baseEnvironment instance;
                path = instance.runtimePackages;
                unitConfig.ConditionPathExists = graphPath instance;
                serviceConfig =
                  commonServiceConfig instance
                  // {
                    ExecStart = serverScript name instance;
                    Restart = "on-failure";
                    RestartSec = "5s";
                    LoadCredential = optional (instance.server.apiKeyFile != null) "mcp-api-key:${toString instance.server.apiKeyFile}";
                  };
              };
            })
          ]
          ++ mapAttrsToList (sink: sinkCfg:
            mkIf sinkCfg.enable {
              "graphify-${name}-${sink}" = {
                description = "Push Graphify graph ${name} to ${sink}";
                after = optional instance.extraction.enable "${extractUnit}.service";
                environment = baseEnvironment instance;
                path = instance.runtimePackages;
                unitConfig.ConditionPathExists = graphPath instance;
                serviceConfig =
                  commonServiceConfig instance
                  // {
                    Type = "oneshot";
                    ExecStart = exportScript name instance sink sinkCfg;
                    LoadCredential = optional (sinkCfg.passwordFile != null) "graph-database-password:${toString sinkCfg.passwordFile}";
                  };
              };
            })
          instance.exports))
      enabledInstances);

      systemd.timers = mkMerge ([
          (mapAttrs' (name: instance:
            nameValuePair "graphify-${name}-extract" {
              wantedBy = ["timers.target"];
              timerConfig = {
                OnCalendar = instance.extraction.onCalendar;
                Persistent = true;
                Unit = "graphify-${name}-extract.service";
              };
            }) (filterAttrs (_: instance: instance.extraction.enable && instance.extraction.onCalendar != null) enabledInstances))
        ]
        ++ flatten (mapAttrsToList (name: instance:
          mapAttrsToList (sink: sinkCfg:
            mkIf (sinkCfg.enable && sinkCfg.onCalendar != null) {
              "graphify-${name}-${sink}" = {
                wantedBy = ["timers.target"];
                timerConfig = {
                  OnCalendar = sinkCfg.onCalendar;
                  Persistent = true;
                  Unit = "graphify-${name}-${sink}.service";
                };
              };
            })
          instance.exports)
        enabledInstances));
    }
  ]);
}
