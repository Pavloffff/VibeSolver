import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const webDist = path.join(desktopRoot, '..', 'web', 'dist');
const webTarget = path.join(desktopRoot, 'web-dist');
const configSource = path.join(desktopRoot, 'src', 'config.html');
const configTarget = path.join(desktopRoot, 'dist', 'config.html');

if (!fs.existsSync(path.join(webDist, 'index.html'))) {
  console.error('Не найдена сборка веб-интерфейса: frontend/web/dist/index.html');
  console.error('Сначала соберите веб-интерфейс: cd frontend/web; npm ci; npm run build');
  process.exit(1);
}

fs.rmSync(webTarget, { recursive: true, force: true });
fs.cpSync(webDist, webTarget, { recursive: true });

fs.mkdirSync(path.dirname(configTarget), { recursive: true });
fs.copyFileSync(configSource, configTarget);

console.log('Веб-сборка скопирована: web-dist; экран настройки обновлён: dist/config.html');
