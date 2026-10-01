import { startAppController } from './app_controller.js';
import { installAppDebugBridge } from './app_debug_bridge.js';

installAppDebugBridge();
startAppController();
