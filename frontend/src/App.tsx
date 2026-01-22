import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { LandingPage } from './pages';

function App() {
  return (
    <BrowserRouter basename="/probablyprofit">
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="*" element={<LandingPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
