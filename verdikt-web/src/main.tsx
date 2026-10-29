import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/global.css';
import { App } from './App';
import {MotionConfig} from 'motion/react';
import {surfaceSpring} from './components/UiState';

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found');

createRoot(root).render(
  <StrictMode>
    <MotionConfig reducedMotion="user" transition={surfaceSpring}><App /></MotionConfig>
  </StrictMode>,
);
