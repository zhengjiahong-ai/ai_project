import { existsSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { cwd } from 'node:process';

const distPath = resolve(cwd(), 'dist');

if (existsSync(distPath)) {
  rmSync(distPath, { recursive: true, force: true });
}
