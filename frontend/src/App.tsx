import { BrowserRouter, Route, Routes } from "react-router-dom";
import Dashboard from "./routes/Dashboard";

// Router shell. Today there is a single dashboard route; deeper-dive pages
// (e.g. /team/:id, /pitcher/:id) drop in as additional <Route> entries without
// touching the existing view.
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
      </Routes>
    </BrowserRouter>
  );
}
