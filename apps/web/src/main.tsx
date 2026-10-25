import { FluentProvider } from "@fluentui/react-components";
import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import Home from "./pages/Home";
import { PrefsProvider, usePrefs } from "./state/prefs";
import "./styles.css";
import { darkTheme, lightTheme } from "./theme";

const HowItWorks = lazy(() => import("./pages/HowItWorks"));
const Check = lazy(() => import("./pages/Check"));
const Studio = lazy(() => import("./pages/Studio"));
const Results = lazy(() => import("./pages/Results"));
const Judges = lazy(() => import("./pages/Judges"));
const Learn = lazy(() => import("./pages/Learn"));
const Developers = lazy(() => import("./pages/Developers"));
const Trust = lazy(() => import("./pages/Trust"));
const Byo = lazy(() => import("./pages/Byo"));
const NotFound = lazy(() => import("./pages/NotFound"));

function Themed() {
  const { dark } = usePrefs();
  return (
    <FluentProvider theme={dark ? darkTheme : lightTheme} className="mh-root" data-theme={dark ? "dark" : "light"}>
      <BrowserRouter>
        <Layout>
          <Suspense fallback={<div className="mh-loading" role="status">Loading the page</div>}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/how-it-works" element={<HowItWorks />} />
              <Route path="/check" element={<Check />} />
              <Route path="/studio" element={<Studio />} />
              <Route path="/results" element={<Results />} />
              <Route path="/judges" element={<Judges />} />
              <Route path="/learn" element={<Learn />} />
              <Route path="/developers" element={<Developers />} />
              <Route path="/trust" element={<Trust />} />
              <Route path="/byo" element={<Byo />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </Layout>
      </BrowserRouter>
    </FluentProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PrefsProvider>
      <Themed />
    </PrefsProvider>
  </StrictMode>,
);
