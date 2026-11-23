import { copyFile } from 'node:fs/promises';

await copyFile(new URL('../src/config.html', import.meta.url), new URL('../dist/config.html', import.meta.url));
