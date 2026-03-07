use std::fmt::Display;

/// A generic wrapper type.
pub struct Wrapper<T> {
    inner: T,
}

impl<T> Wrapper<T> {
    pub fn new(value: T) -> Self {
        Wrapper { inner: value }
    }

    pub fn into_inner(self) -> T {
        self.inner
    }
}

impl<T: Display> Wrapper<T> {
    pub fn display(&self) -> String {
        format!("{}", self.inner)
    }
}

pub fn maximum<T: PartialOrd>(a: T, b: T) -> T {
    if a > b { a } else { b }
}

pub fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

pub fn process<T>(item: T) -> String
where
    T: Display + Clone,
{
    let cloned = item.clone();
    format!("{} (cloned: {})", item, cloned)
}

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_wrapper_new() {
        let w = Wrapper::new(42);
        assert_eq!(w.into_inner(), 42);
    }

    #[test]
    fn test_wrapper_display() {
        let w = Wrapper::new("hello");
        assert_eq!(w.display(), "hello");
    }

    #[test]
    fn test_maximum() {
        assert_eq!(maximum(3, 5), 5);
        assert_eq!(maximum(10, 2), 10);
    }

    #[test]
    fn test_longest() {
        assert_eq!(longest("short", "longer"), "longer");
    }
}
