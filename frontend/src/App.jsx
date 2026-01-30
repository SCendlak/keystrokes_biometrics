import { useRef, useState, useEffect } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";

const TRAIN_TEXT = "Analiza wzorców pisania na klawiaturze to metoda biometryczna analizująca rytm i sposób naciskania klawiszy. Uwzględnia ona czas reakcji, przerwy i siłę uderzeń. Służy do identyfikacji użytkownika po jego unikalnym sposobie pisania.";
const TEST_TEXTS = [
  "To jest krótki test weryfikacyjny użytkownika. Analizowane są wzorce pisania metodą odległości Manhatanskiej"
];

function App() {

  const [view, setView] = useState("home");
  const [username, setUsername] = useState("");
  const [trainCount, setTrainCount] = useState(0);

  const keyDownTimes = useRef({});
  const sessionStartTime = useRef(null);
  const textAreaRef = useRef(null);

  const [isRecording, setIsRecording] = useState(false);
  const [keystrokeData, setKeystrokeData] = useState([]);
  const [text, setText] = useState(""); // Visual text
  const [targetText, setTargetText] = useState("");
  const [isCompleted, setIsCompleted] = useState(false);


  const [lastResponse, setLastResponse] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [verificationMatrix, setVerificationMatrix] = useState(null);




  useEffect(() => {
    if (view === "train") {
      setTargetText(TRAIN_TEXT);
      if (username) fetchStats();
      resetInternalState();
    } else if (view === "test") {
      setTargetText(TEST_TEXTS[Math.floor(Math.random() * TEST_TEXTS.length)]);
      resetInternalState();
    }
  }, [view]);


  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/users/${username}/stats`);
      if (res.ok) {
        const data = await res.json();
        setTrainCount(data.sessionCount);
      }
    } catch (e) {
      console.error("Failed to fetch stats", e);
    }
  };

  const resetInternalState = () => {
    setIsRecording(false);
    setIsCompleted(false);
    sessionStartTime.current = null;
    keyDownTimes.current = {};
    setKeystrokeData([]);
    setText("");
    setLastResponse(null);
    setVerificationMatrix(null);
    setErrorMsg("");

    setTimeout(() => {
      if (textAreaRef.current) textAreaRef.current.focus();
    }, 50);
  };

  const startSession = () => {
    if (!sessionStartTime.current) {
      sessionStartTime.current = Date.now();
      setIsRecording(true);
      setKeystrokeData([]);
      setText("");
      keyDownTimes.current = {};
      setIsCompleted(false);
      setErrorMsg("");
    }
  };

  const stopSession = async () => {
    setIsRecording(false);
    setIsCompleted(true);
    if (keystrokeData.length > 0) {
      await submitData();
    }
  };

  const submitData = async () => {
    if (!keystrokeData.length) return;

    const payload = {
      userId: username,
      text,
      startedAt: new Date().toISOString(),
      keystrokes: keystrokeData,
    };

    const endpoint = view === "test" ? `${API_BASE}/api/verify` : `${API_BASE}/api/sessions`;

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      if (!res.ok) {
        setErrorMsg(data.detail);
        return;
      }

      setLastResponse(data);

      if (view === "train") {
        await fetchStats();

      } else if (view === "test") {
        setVerificationMatrix(data);
      }
    } catch (error) {
      console.error("Error submitting data:", error);
      setErrorMsg("Network error - could not connect to API");
    }
  };


  const handleKeyDown = (e) => {
    if (!isRecording && !isCompleted) {
        startSession();
    }

    if (!isRecording) return;

    if (e.key === "Enter") {
      e.preventDefault();
      stopSession();
      return;
    }

    if (e.key === "Backspace") {
      if (keystrokeData.length > 0) {
        setKeystrokeData((prev) => prev.slice(0, -1));
      }
      return;
    }

    if (
        e.key.startsWith("F") && e.key.length > 1 ||
        e.key === "Escape" ||
        e.key === "Tab" ||
        e.metaKey ||
        e.ctrlKey
    ) {
        e.preventDefault();
        return;
    }

    if (e.key.length === 1 || e.key === "Space") {
        const key = e.key;
        const timestamp = Date.now() - sessionStartTime.current;

        if (e.repeat) return;

        if (!keyDownTimes.current[key]) {
            keyDownTimes.current[key] = timestamp;
        }
    }
  };

  const handleKeyUp = (e) => {
    if (!isRecording) return;

    if (e.key.length !== 1 && e.key !== "Space") return;

    const key = e.key;
    const timestamp = Date.now() - sessionStartTime.current;
    const keyDownTime = keyDownTimes.current[key];

    if (keyDownTime !== undefined) {
      const dwellTime = timestamp - keyDownTime;

      const flightTime =
        keystrokeData.length > 0
          ? keyDownTime - keystrokeData[keystrokeData.length - 1].releaseTime
          : 0;

      const keystroke = {
        key: key === " " ? "Space" : key,
        keyCode: String(e.keyCode || 0),
        pressTime: keyDownTime,
        releaseTime: timestamp,
        dwellTime,
        flightTime,
      };

      setKeystrokeData((prev) => [...prev, keystroke]);
      delete keyDownTimes.current[key];
    }
  };

  const handleChange = (e) => {
    if (!isRecording) return;
    setText(e.target.value);
  };


  const renderText = () => {
    const chars = targetText.split("");
    const typed = text.split("");

    return chars.map((char, idx) => {
      let className = "";
      let displayChar = char;

      if (idx < typed.length) {
        if (typed[idx] === char) {
          className = "correct";
        } else {
          className = "incorrect";
        }
      } else if (idx === typed.length) {
        className = "cursor";
      }

      if (char === " ") {
        displayChar = "\u0020";
        if (className === "") className = "space-char inactive";
        else className += " space-char";
      }

      return (
        <span key={idx} className={className}>
          {displayChar}
        </span>
      );
    });
  };

  if (view === "home") {
    return (
      <div className="container" style={{ textAlign: "center", marginTop: 50 }}>
        <h1>Keystroke Biometrics</h1>
        <div style={{ display: "flex", flexDirection: "column", gap: 15, maxWidth: 300, margin: "0 auto" }}>
          <input
            type="text"
            placeholder="Enter Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ padding: 12, fontSize: 16, borderRadius: 4, border: "1px solid #444", background: "#222", color: "white" }}
          />
          <button
            disabled={!username}
            onClick={() => setView("train")}
            className="btn-primary"
            style={{ backgroundColor: "#4ade80", color: "black" }}
          >
            TRAIN (Enrollment)
          </button>
          <button
            disabled={!username}
            onClick={() => setView("test")}
            className="btn-primary"
            style={{ backgroundColor: "#60a5fa", color: "black" }}
          >
            TEST (Verification)
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="container" style={{ maxWidth: 900, margin: "0 auto", padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <button onClick={() => setView("home")} style={{ background: "transparent", border: "1px solid #444", color: "#ccc" }}>
          Cofnij
        </button>
        <div>Użytkonik: <strong>{username}</strong></div>
      </div>

      <h1>{view === "train" ? "Sesja Treningowa" : "Werifikacja"}</h1>

      {view === "train" && (
        <div style={{ marginBottom: 20, padding: 15, background: "#1a1a1a", borderRadius: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, fontSize: 14 }}>
            <span>Progres</span>
            <span>{trainCount} / 3 sesji</span>
          </div>
          <div style={{ width: "100%", height: 8, background: "#333", borderRadius: 4 }}>
            <div style={{
              width: `${Math.min(100, (trainCount / 3) * 100)}%`,
              height: "100%",
              background: trainCount >= 3 ? "#4ade80" : "#fbbf24",
              borderRadius: 4,
              transition: "width 0.5s ease"
            }} />
          </div>
        </div>
      )}

      {errorMsg && (
        <div style={{ padding: 15, background: "rgba(127, 29, 29, 0.5)", border: "1px solid #ef4444", color: "#fca5a5", borderRadius: 8, marginBottom: 20 }}>
          {errorMsg}
        </div>
      )}


      <div style={{ position: "relative", marginBottom: 20 }}>
        <div
          style={{
            padding: 24,
            backgroundColor: "#111",
            borderRadius: 8,
            fontSize: 24,
            lineHeight: 1.6,
            fontFamily: "monospace",
            minHeight: 150,
            border: isRecording ? "2px solid #4ade80" : "2px solid #333",
            transition: "border-color 0.3s",
            whiteSpace: "pre-wrap",
            color: "#555"
          }}
        >
          {renderText()}
        </div>
        <textarea
          ref={textAreaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onKeyUp={handleKeyUp}
          disabled={isCompleted}
          spellCheck={false}
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            opacity: 0,
            cursor: isCompleted ? "default" : "text",
            resize: "none",
          }}
        />
      </div>

      <div style={{ textAlign: "center", fontSize: 14, opacity: 0.7, marginBottom: 20 }}>
        {!isRecording && !isCompleted && "Zacznij pisać aby zacząć..."}
        {isRecording && "Naciśnij ENTER aby skończyć"}
        {isCompleted && "Sesja skończona"}
      </div>

      {isCompleted && (
        <button
          onClick={resetInternalState}
          style={{ width: "100%", padding: 15, background: "#333", color: "white", fontSize: 16, cursor: "pointer" }}
        >
          {view === "train" ? "Trenuj dalej!" : "Sprawdź ponownie"}
        </button>
      )}

      {view === "test" && verificationMatrix && (
        <div style={{ marginTop: 30, animation: "fadeIn 0.5s" }}>
          <h2>Tabela podobieństw:</h2>
          <div style={{ overflowX: "auto" }}>
            <p style={{border: 1, borderStyle: "solid", borderColor: "gray", borderRadius: 8}}> Warto zaznaczyć że różnice mogą się wachać w przedziałach 40-80ms</p>
            <table style={{ width: "100%", borderCollapse: "collapse", background: "#111", borderRadius: 8 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #333", color: "#888", textAlign: "left" }}>
                  <th style={{ padding: 12 }}>ID Użytkownika</th>
                  <th style={{ padding: 12 }}>Wynik różnic</th>
                  <th style={{ padding: 12 }}>Wskaźnik Pewności</th>
                </tr>
              </thead>
              <tbody>
                {verificationMatrix.matrix.map((match, idx) => (
                  <tr key={idx} style={{
                    borderBottom: "1px solid #222",
                    backgroundColor: match.userId === username ? "rgba(74, 222, 128, 0.1)" : "transparent",
                    color: match.userId === username ? "#fff" : "#888"
                  }}>
                    <td style={{ padding: 12 }}>
                      {match.userId}
                      {idx === 0 && <span style={{ marginLeft: 8 }}>🏆</span>}
                    </td>
                    <td style={{ padding: 12 }}>{match.score.toFixed(2)}</td>
                    <td style={{ padding: 12, color: match.confidence > 80 ? "#4ade80" : match.confidence > 50 ? "#fbbf24" : "#ef4444" }}>
                      {match.confidence}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{
            marginTop: 20,
            padding: 15,
            textAlign: "center",
            borderRadius: 8,
            background: verificationMatrix.verified ? "rgba(74, 222, 128, 0.1)" : "rgba(239, 68, 68, 0.1)",
            border: `1px solid ${verificationMatrix.verified ? "#4ade80" : "#ef4444"}`,
            color: verificationMatrix.verified ? "#4ade80" : "#ef4444",
            fontWeight: "bold"
          }}>
            {verificationMatrix.verified
              ? `Znaleziono Użytkownika: ${username}`
              : `Niezgodność Tożsamości, błąd identyfikacji `
            }
          </div>
        </div>
      )}

      <div style={{ marginTop: 40, fontSize: 12, color: "#444", textAlign: "right" }}>
        DEBUG: zebrano: {keystrokeData.length} wciśnięć ze znaków: {text.length}
      </div>

      <style>{`
        .correct { color: #4ade80; }
        .incorrect { color: #ef4444; background-color: rgba(239, 68, 68, 0.2); }
        .cursor { border-left: 2px solid #60a5fa; animation: blink 1s infinite; }
        .space-char { opacity: 0.3; }
        .btn-primary { padding: 15px; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; transition: opacity 0.2s; }
        .btn-primary:hover:not(:disabled) { opacity: 0.9; }
        .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
        @keyframes blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  );
}

export default App;