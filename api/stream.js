export default async function handler(req, res) {
  const { url } = req.query;

  if (!url) {
    return res.status(400).json({ error: "Missing ?url parameter" });
  }

  try {
    const response = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": url,
        "Origin": new URL(url).origin,
      },
    });

    if (!response.ok) {
      return res.status(response.status).json({
        error: "Failed to fetch stream",
        status: response.status,
      });
    }

    const data = await response.text();

    res.setHeader("Content-Type", "application/vnd.apple.mpegurl");
    res.status(200).send(data);

  } catch (error) {
    res.status(500).json({
      error: "Server error",
      message: error.message,
    });
  }
}
