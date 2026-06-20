import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// Public dir is supplied per-render via --public-dir (repo root) so the
// renderer can reach clips in output/ and brand assets in assets/.
