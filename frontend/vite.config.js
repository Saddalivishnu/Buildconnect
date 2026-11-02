import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, '.', '');
    return {
        plugins: [react()],
        server: {
            proxy: {
                '/api': {
                    target: env.VITE_PROXY_TARGET || 'http://localhost:5000',
                    changeOrigin: true,
                },
            },
        },
    };
});
