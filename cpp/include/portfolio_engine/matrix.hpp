#pragma once

#include <cstddef>
#include <span>
#include <stdexcept>
#include <vector>

namespace portfolio_engine {

class MatrixView {
 public:
  MatrixView(std::span<const double> data, std::size_t rows, std::size_t columns)
      : data_(data), rows_(rows), columns_(columns) {
    if (rows_ != 0 && columns_ > data_.size() / rows_) {
      throw std::invalid_argument("matrix dimensions overflow");
    }
    if (rows_ * columns_ != data_.size()) {
      throw std::invalid_argument("matrix data size does not match its shape");
    }
  }

  [[nodiscard]] double operator()(std::size_t row, std::size_t column) const {
    return data_[row * columns_ + column];
  }
  [[nodiscard]] std::span<const double> row(std::size_t index) const {
    return data_.subspan(index * columns_, columns_);
  }
  [[nodiscard]] std::span<const double> data() const { return data_; }
  [[nodiscard]] std::size_t rows() const { return rows_; }
  [[nodiscard]] std::size_t columns() const { return columns_; }

 private:
  std::span<const double> data_;
  std::size_t rows_;
  std::size_t columns_;
};

struct Matrix {
  std::size_t rows{};
  std::size_t columns{};
  std::vector<double> data;

  [[nodiscard]] double operator()(std::size_t row, std::size_t column) const {
    return data[row * columns + column];
  }
  [[nodiscard]] double& operator()(std::size_t row, std::size_t column) {
    return data[row * columns + column];
  }
  [[nodiscard]] MatrixView view() const { return MatrixView(data, rows, columns); }
};

}  // namespace portfolio_engine
