{
  pkgs,
  treefmtWrapper,
  rustToolchain ? null,
}: {
  treefmt = {
    enable = true;
    name = "treefmt";
    entry = "${treefmtWrapper}/bin/treefmt --fail-on-change";
    pass_filenames = false;
  };

  cargo-fmt = {
    enable = true;
    name = "cargo fmt";
    entry = "cargo fmt --all -- --check";
    extraPackages = pkgs.lib.optional (rustToolchain != null) rustToolchain;
    pass_filenames = false;
  };

  cargo-clippy = {
    enable = true;
    name = "cargo clippy";
    entry = "cargo clippy --all-targets --all-features -- --deny warnings";
    extraPackages = pkgs.lib.optional (rustToolchain != null) rustToolchain;
    pass_filenames = false;
  };

  cargo-audit = {
    enable = true;
    name = "cargo audit";
    entry = "cargo audit";
    extraPackages = pkgs.lib.optional (rustToolchain != null) rustToolchain ++ [pkgs.cargo-audit];
    pass_filenames = false;
  };

  nix-flake-check = {
    enable = true;
    name = "nix flake check";
    entry = "nix --extra-experimental-features 'nix-command flakes' flake check --cores 0 --max-jobs auto --no-update-lock-file";
    extraPackages = [pkgs.nix];
    pass_filenames = false;
    stages = ["manual"];
  };

  uv-ruff-format = {
    enable = true;
    name = "uv ruff format";
    entry = "uv run ruff format --check .";
    extraPackages = [pkgs.uv];
    pass_filenames = false;
  };

  uv-mypy = {
    enable = true;
    name = "uv mypy";
    entry = "uv run mypy .";
    extraPackages = [pkgs.uv];
    pass_filenames = false;
  };
}
