import * as svc from "./service";
import { handleCreate } from "./handler";

export function main(): void {
  handleCreate("Alice");
  svc.deleteUser(1);
  svc.updateUser(2, "Bob");
}
