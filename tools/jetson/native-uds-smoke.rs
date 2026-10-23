use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;
use tokio::time::{timeout, Duration};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    timeout(Duration::from_secs(3), async {
        let (mut client, mut server) = UnixStream::pair()?;
        let echo = tokio::spawn(async move {
            let mut data = [0u8; 4];
            server.read_exact(&mut data).await?;
            server.write_all(&data).await
        });
        client.write_all(b"nano").await?;
        let mut data = [0u8; 4];
        client.read_exact(&mut data).await?;
        assert_eq!(&data, b"nano");
        echo.await??;
        Ok::<(), Box<dyn std::error::Error>>(())
    }).await??;
    println!("Tokio AF_UNIX native roundtrip OK on {}", std::env::consts::ARCH);
    Ok(())
}
