import { http } from "msw";

import { getDb } from "@/mocks/db";
import { demoJson, v1 } from "@/mocks/http";

export const setupHandlers = [http.get(v1("/setup/profile"), () => demoJson(getDb().profile))];
