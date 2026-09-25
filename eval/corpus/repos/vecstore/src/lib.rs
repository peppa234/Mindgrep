//! A tiny exact nearest-neighbour vector store, written to understand what ANN indexes
//! approximate. Brute force, but with a bounded heap so top-k is O(n log k).

use std::cmp::Ordering;
use std::collections::BinaryHeap;

use serde::{Deserialize, Serialize};

/// Cosine similarity between two vectors of equal length. Returns 0.0 for a zero vector.
pub fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    assert_eq!(a.len(), b.len(), "vectors must have the same dimension");
    let mut dot = 0.0;
    let mut norm_a = 0.0;
    let mut norm_b = 0.0;
    for (x, y) in a.iter().zip(b) {
        dot += x * y;
        norm_a += x * x;
        norm_b += y * y;
    }
    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }
    dot / (norm_a.sqrt() * norm_b.sqrt())
}

#[derive(Debug, PartialEq)]
struct Scored {
    score: f32,
    id: u64,
}

impl Eq for Scored {}

// Reversed ordering: BinaryHeap is a max-heap, we want the *worst* of the current top-k on top
// so it can be evicted cheaply.
impl Ord for Scored {
    fn cmp(&self, other: &Self) -> Ordering {
        other.score.partial_cmp(&self.score).unwrap_or(Ordering::Equal)
    }
}

impl PartialOrd for Scored {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

#[derive(Default, Serialize, Deserialize)]
pub struct VecStore {
    dim: usize,
    ids: Vec<u64>,
    vectors: Vec<Vec<f32>>,
}

impl VecStore {
    pub fn new(dim: usize) -> Self {
        Self { dim, ..Default::default() }
    }

    pub fn insert(&mut self, id: u64, vector: Vec<f32>) {
        assert_eq!(vector.len(), self.dim);
        self.ids.push(id);
        self.vectors.push(vector);
    }

    /// The k most similar stored vectors to `query`, best first.
    pub fn search(&self, query: &[f32], k: usize) -> Vec<(u64, f32)> {
        let mut heap: BinaryHeap<Scored> = BinaryHeap::with_capacity(k + 1);
        for (id, vector) in self.ids.iter().zip(&self.vectors) {
            heap.push(Scored { score: cosine_similarity(query, vector), id: *id });
            if heap.len() > k {
                heap.pop();
            }
        }
        let mut results: Vec<(u64, f32)> = heap.into_iter().map(|s| (s.id, s.score)).collect();
        results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(Ordering::Equal));
        results
    }

    /// Persist the whole store to bytes with bincode.
    pub fn to_bytes(&self) -> Vec<u8> {
        bincode::serialize(self).expect("serializable")
    }

    pub fn from_bytes(bytes: &[u8]) -> Self {
        bincode::deserialize(bytes).expect("valid vecstore bytes")
    }
}
