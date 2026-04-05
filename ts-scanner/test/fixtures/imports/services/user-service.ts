import { User } from "../models/user";
import { AuthService } from "./auth-service";
import { logger } from "../utils/logger";
import bcrypt from "bcrypt";

export class UserService {
  constructor(private auth: AuthService) {}
}