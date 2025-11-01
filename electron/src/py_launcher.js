const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

function findBundledPython() {
  // When packaged, resources are under process.resourcesPath
  const resources = process.resourcesPath || process.cwd();
  // Common location when bundling a Python runtime: resources/python/python.exe
  const candidates = [];
  if (process.platform === 'win32') {
    candidates.push(path.join(resources, 'python', 'python.exe'));
    candidates.push(path.join(resources, 'python.exe'));
  } else {
    candidates.push(path.join(resources, 'python', 'bin', 'python3'));
    candidates.push(path.join(resources, 'python', 'bin', 'python'));
  }

  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return c;
    } catch (e) {
      // ignore
    }
  }

  // Fallback to system python
  return process.platform === 'win32' ? 'python' : 'python3';
}

function startApiServer(apiRelativePath) {
  return new Promise((resolve, reject) => {
    const pythonExec = findBundledPython();
    const apiPath = path.isAbsolute(apiRelativePath) ? apiRelativePath : path.join(__dirname, '..', '..', apiRelativePath);

    try {
      const env = Object.assign({}, process.env, { PYTHONUNBUFFERED: '1' });

      const child = spawn(pythonExec, [apiPath], {
        env,
        cwd: path.dirname(apiPath),
        stdio: ['ignore', 'pipe', 'pipe']
      });

      const onData = (data) => {
        const s = data.toString();
        // Detect a likely Flask startup message
        if (s.toLowerCase().includes('running on') || s.toLowerCase().includes('serving')) {
          cleanupListeners();
          resolve(child);
        }
      };

      const onError = (data) => {
        // forward stderr but don't reject immediately
        // reject if we see fatal import errors
        const s = data.toString();
        if (/traceback|error/i.test(s)) {
          // keep listening; but also log
        }
      };

      const onClose = (code) => {
        cleanupListeners();
        // resolve even if it closed early so caller can handle
        resolve(null);
      };

      function cleanupListeners() {
        if (child.stdout) child.stdout.removeListener('data', onData);
        if (child.stderr) child.stderr.removeListener('data', onError);
        child.removeListener('close', onClose);
      }

      child.stdout && child.stdout.on('data', onData);
      child.stderr && child.stderr.on('data', onError);
      child.on('close', onClose);

      // Safety: if nothing after 6s, resolve with child so app can try to poll
      setTimeout(() => resolve(child), 6000);
    } catch (err) {
      reject(err);
    }
  });
}

module.exports = { startApiServer };
