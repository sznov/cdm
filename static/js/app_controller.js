import { createComposedAppController } from './app_controller_composition.js';

const appController = createComposedAppController();

export function startAppController() {
  return appController.startAppController();
}

export default startAppController;

