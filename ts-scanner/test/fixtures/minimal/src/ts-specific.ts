// @ts-ignore
const x: any = 42;
const y = x as any;
// @ts-expect-error
const z: string = 42 as unknown as string;

import { readFileSync } from "fs";
const bar = require("./bar");

declare module "express" {
  interface Request {
    user: any;
  }
}

declare global {
  interface Window {
    __APP_STATE__: any;
  }
}

namespace Legacy {
  export function helper(): void {}
}

export namespace Exported {
  export const VALUE = 1;
}
