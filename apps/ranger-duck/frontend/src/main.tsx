import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';

// The simulator owns a single imperative physics loop. Avoid development-only
// StrictMode remounts that boot two WASM runtimes before the first has disposed.
ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
