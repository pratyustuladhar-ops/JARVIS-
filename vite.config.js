import { resolve } from 'path';
import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    host: 'localhost',
  },
  plugins: [
    {
      name: 'root-redirect-to-assistant',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url === '/' || req.url === '/index.html') {
            res.writeHead(302, { Location: '/assistant.html' });
            res.end();
            return;
          }
          next();
        });
      },
    },
  ],
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        assistant: resolve(__dirname, 'assistant.html'),
        tasks: resolve(__dirname, 'tasks.html'),
        projects: resolve(__dirname, 'projects.html'),
        memory: resolve(__dirname, 'memory.html'),
        activity: resolve(__dirname, 'activity.html'),
        settings: resolve(__dirname, 'settings.html'),
        cms: resolve(__dirname, 'cms.html'),
      },
    },
  },
});

