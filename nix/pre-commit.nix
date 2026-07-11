{
  pkgs,
  treefmtWrapper,
}: {
  treefmt = {
    enable = true;
    name = "treefmt";
    entry = "${treefmtWrapper}/bin/treefmt --fail-on-change";
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
}
