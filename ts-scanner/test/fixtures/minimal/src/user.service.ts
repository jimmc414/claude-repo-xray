/**
 * User service — handles user CRUD operations.
 */

export interface User {
  id: number;
  name: string;
  email: string;
  role: "admin" | "user" | "guest";
  createdAt?: Date;
}

export type UserCreateInput = Pick<User, "name" | "email">;

export enum UserRole {
  Admin = "admin",
  User = "user",
  Guest = "guest",
}

const DEFAULT_ROLE = UserRole.User;

export class UserService {
  private users: User[] = [];
  private nextId = 1;

  /** Initialize the service with seed data. */
  async initialize(): Promise<void> {
    this.users = [];
    this.nextId = 1;
  }

  /**
   * Create a new user.
   * Validates the input and assigns a unique ID.
   */
  async createUser(input: UserCreateInput, role: UserRole = DEFAULT_ROLE): Promise<User> {
    if (!input.name || !input.email) {
      throw new Error("Name and email are required");
    }

    const user: User = {
      id: this.nextId++,
      name: input.name,
      email: input.email,
      role,
      createdAt: new Date(),
    };

    this.users.push(user);
    return user;
  }

  /** Find a user by ID. */
  findById(id: number): User | undefined {
    return this.users.find(u => u.id === id);
  }

  /**
   * Find users matching a filter.
   * Supports filtering by role and partial name match.
   */
  findUsers(filter?: { role?: UserRole; nameContains?: string }): User[] {
    if (!filter) return [...this.users];

    return this.users.filter(u => {
      if (filter.role && u.role !== filter.role) return false;
      if (filter.nameContains && !u.name.toLowerCase().includes(filter.nameContains.toLowerCase())) return false;
      return true;
    });
  }

  /** Delete a user by ID. Returns true if found and deleted. */
  deleteUser(id: number): boolean {
    const index = this.users.findIndex(u => u.id === id);
    if (index === -1) return false;
    this.users.splice(index, 1);
    return true;
  }

  /** Get total user count. */
  get count(): number {
    return this.users.length;
  }
}
