export function createUser(name: string): { id: number; name: string } {
  return { id: Math.random(), name };
}

export function deleteUser(id: number): boolean {
  console.log(`Deleting user ${id}`);
  return true;
}

export function updateUser(id: number, name: string): void {
  console.log(`Updating user ${id} to ${name}`);
}
