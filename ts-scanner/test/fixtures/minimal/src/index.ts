/**
 * Application entry point.
 * Sets up an Express server and starts listening.
 */

import { UserService } from "./user.service";
import { formatName, MAX_RETRIES } from "./utils";

const PORT = 3000;

export class App {
  private userService: UserService;

  constructor() {
    this.userService = new UserService();
  }

  /** Start the application server. */
  async start(): Promise<void> {
    console.log(`Starting on port ${PORT}`);
    await this.userService.initialize();
  }

  getStatus(): { running: boolean; port: number } {
    return { running: true, port: PORT };
  }
}

export async function bootstrap(): Promise<App> {
  const app = new App();
  await app.start();
  return app;
}

// Simple sync function
export function getVersion(): string {
  return "1.0.0";
}
