use std::io;

pub async fn fetch_data(url: &str) -> Result<String, io::Error> {
    // Simulated async fetch
    Ok(format!("data from {}", url))
}

pub async fn process_batch(items: Vec<String>) -> Vec<String> {
    let mut results = Vec::new();
    for item in items {
        results.push(format!("processed: {}", item));
    }
    results
}

pub unsafe fn raw_pointer_deref(ptr: *const i32) -> i32 {
    *ptr
}

pub const fn const_add(a: u32, b: u32) -> u32 {
    a + b
}

#[derive(Debug, Clone)]
pub struct Config {
    pub host: String,
    pub port: u16,
    pub timeout_ms: u64,
    pub retry_count: u32,
}

impl Config {
    pub fn default_config() -> Self {
        Config {
            host: "localhost".to_string(),
            port: 8080,
            timeout_ms: 5000,
            retry_count: 3,
        }
    }

    pub fn with_host(mut self, host: &str) -> Self {
        self.host = host.to_string();
        self
    }

    pub fn with_port(mut self, port: u16) -> Self {
        self.port = port;
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_fetch_data() {
        let result = fetch_data("http://example.com").await.unwrap();
        assert!(result.contains("example.com"));
    }

    #[test]
    fn test_const_add() {
        assert_eq!(const_add(2, 3), 5);
    }

    #[test]
    fn test_config_default() {
        let config = Config::default_config();
        assert_eq!(config.port, 8080);
    }

    #[test]
    fn test_config_builder() {
        let config = Config::default_config()
            .with_host("example.com")
            .with_port(9090);
        assert_eq!(config.host, "example.com");
        assert_eq!(config.port, 9090);
    }
}
