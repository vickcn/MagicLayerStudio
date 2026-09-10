const fs = require('fs');
const path = require('path');

function main() {
  const packageJsonPath = require.resolve('@fontsource/lxgw-wenkai-tc/package.json');
  const sourceRoot = path.dirname(packageJsonPath);
  const targetRoot = path.join(__dirname, '..', 'web', 'frontend', 'fonts', 'lxgw');
  const targetFilesDir = path.join(targetRoot, 'files');

  fs.mkdirSync(targetFilesDir, { recursive: true });
  fs.copyFileSync(
    path.join(sourceRoot, 'index.css'),
    path.join(targetRoot, 'lxgwwenkaitc-regular.css')
  );
  fs.cpSync(path.join(sourceRoot, 'files'), targetFilesDir, { recursive: true, force: true });

  console.log(`Copied LXGW WenKai TC assets to ${targetRoot}`);
}

main();
