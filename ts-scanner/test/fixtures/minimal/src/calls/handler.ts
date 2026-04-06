import { createUser, updateUser } from "./service";

export function handleCreate(name: string): void {
  const user = createUser(name);
  console.log(`Created user: ${user.name}`);
}

export function handleUpdate(id: number, name: string): void {
  updateUser(id, name);
}
