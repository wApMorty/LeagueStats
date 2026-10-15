// Remotion (SPEC-34 §4.6) : les captures et leur manifeste sont lus là où capture_screens.py les écrit.
import { Config } from "@remotion/cli/config";

Config.setPublicDir("../../images/captures");
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
