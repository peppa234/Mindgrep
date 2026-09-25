package com.example.inventory;

import java.util.Optional;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private static final int MAX_RETRIES = 3;

    private final ProductRepository products;

    public InventoryService(ProductRepository products) {
        this.products = products;
    }

    /**
     * Reserve stock for an order. Products carry a @Version column, so two concurrent
     * reservations of the last unit cannot both succeed: the second commit fails with an
     * optimistic locking exception and is retried against fresh data.
     */
    public boolean reserveStock(long productId, int quantity) {
        for (int attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
                return tryReserve(productId, quantity);
            } catch (OptimisticLockingFailureException e) {
                if (attempt == MAX_RETRIES) {
                    throw e;
                }
            }
        }
        return false;
    }

    @Transactional
    protected boolean tryReserve(long productId, int quantity) {
        Optional<Product> found = products.findById(productId);
        if (found.isEmpty()) {
            return false;
        }
        Product product = found.get();
        if (product.getAvailable() < quantity) {
            return false;
        }
        product.setAvailable(product.getAvailable() - quantity);
        products.save(product);
        return true;
    }

    /** Put reserved units back, e.g. when an order is cancelled or its payment fails. */
    @Transactional
    public void releaseStock(long productId, int quantity) {
        products.findById(productId).ifPresent(product -> {
            product.setAvailable(product.getAvailable() + quantity);
            products.save(product);
        });
    }
}
