import React from 'react';
import { createRoot } from 'react-dom/client';
import OrchestraApp from '@/OrchestraApp';
import '@/styles/orchestra.css';

const root = createRoot(document.getElementById('root')!);
root.render(<OrchestraApp />);
