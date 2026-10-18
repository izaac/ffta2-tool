{
  description = "FFTA2 save editor and melonDS e2e harness dev environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            # repo workflow
            just
            python3
            ruff
            shellcheck
            # melonDS e2e driver toolchain used by examples/melonds/e2e/mds.sh
            melonds
            xdotool
            xvfb
            gdb
            imagemagick
          ];
          shellHook = ''
            echo "ffta2-tool devenv: just --list, just check, nix-shell tools preloaded (MDS_EXTRA_PATH not needed)"
          '';
        };
      });
    };
}
