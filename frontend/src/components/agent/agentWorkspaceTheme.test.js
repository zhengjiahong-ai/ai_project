import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcRoot = path.resolve(__dirname, '..', '..');
const agentDir = __dirname;
const navbarPath = path.join(srcRoot, 'components', 'Navbar.jsx');

const filesToScan = [
  ...fs
    .readdirSync(agentDir)
    .filter((fileName) => fileName.endsWith('.jsx'))
    .map((fileName) => path.join(agentDir, fileName)),
  navbarPath,
];

const forbiddenThemeTokens = [
  'bg-white/',
  'text-slate-',
  'border-slate-',
  'bg-[#fb',
  'bg-[#fc',
  'border-[#e',
];

const violations = [];

for (const filePath of filesToScan) {
  const source = fs.readFileSync(filePath, 'utf8');
  for (const token of forbiddenThemeTokens) {
    if (source.includes(token)) {
      violations.push(`${path.relative(srcRoot, filePath)} contains ${token}`);
    }
  }
}

assert.deepEqual(
  violations,
  [],
  `Agent workspace and mode switch should use theme-aware classes:\n${violations.join('\n')}`,
);

console.log('agentWorkspaceTheme tests passed');
