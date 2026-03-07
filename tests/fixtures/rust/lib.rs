/// A 2D point.
pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    pub fn new(x: f64, y: f64) -> Self {
        Point { x, y }
    }

    pub fn distance(&self, other: &Point) -> f64 {
        ((self.x - other.x).powi(2) + (self.y - other.y).powi(2)).sqrt()
    }

    pub fn origin() -> Self {
        Point { x: 0.0, y: 0.0 }
    }
}

pub enum Shape {
    Circle(f64),
    Rectangle(f64, f64),
    Triangle { base: f64, height: f64 },
}

impl Shape {
    pub fn area(&self) -> f64 {
        match self {
            Shape::Circle(r) => std::f64::consts::PI * r * r,
            Shape::Rectangle(w, h) => w * h,
            Shape::Triangle { base, height } => 0.5 * base * height,
        }
    }
}

pub trait Drawable {
    fn draw(&self);
    fn bounding_box(&self) -> (f64, f64, f64, f64);
}

impl Drawable for Point {
    fn draw(&self) {
        println!("Point({}, {})", self.x, self.y);
    }

    fn bounding_box(&self) -> (f64, f64, f64, f64) {
        (self.x, self.y, self.x, self.y)
    }
}

pub const MAX_POINTS: usize = 1024;
pub static ORIGIN: Point = Point { x: 0.0, y: 0.0 };
pub type PointPair = (Point, Point);

macro_rules! make_point {
    ($x:expr, $y:expr) => {
        Point::new($x, $y)
    };
}

mod helpers {
    pub fn clamp(value: f64, min: f64, max: f64) -> f64 {
        if value < min {
            min
        } else if value > max {
            max
        } else {
            value
        }
    }

    pub fn lerp(a: f64, b: f64, t: f64) -> f64 {
        a + (b - a) * t
    }

    pub const EPSILON: f64 = 1e-10;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_point_new() {
        let p = Point::new(3.0, 4.0);
        assert_eq!(p.x, 3.0);
        assert_eq!(p.y, 4.0);
    }

    #[test]
    fn test_point_distance() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(3.0, 4.0);
        assert!((a.distance(&b) - 5.0).abs() < 1e-10);
    }

    #[test]
    fn test_circle_area() {
        let c = Shape::Circle(1.0);
        assert!((c.area() - std::f64::consts::PI).abs() < 1e-10);
    }

    #[test]
    fn test_rectangle_area() {
        let r = Shape::Rectangle(3.0, 4.0);
        assert!((r.area() - 12.0).abs() < 1e-10);
    }

    #[test]
    fn test_origin() {
        let p = Point::origin();
        assert_eq!(p.x, 0.0);
        assert_eq!(p.y, 0.0);
    }
}
