import { UserService } from "./user-service";
import { logger } from "../utils/logger";

export class AuthService {
  constructor(private users: UserService) {}
}